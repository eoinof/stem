"""
Supports message based communication with sockets speaking the tor control
protocol. This lets users send messages as basic strings and receive responses
as instances of the :class:`~stem.response.ControlMessage` class.

**Module Overview:**

::

  ControlSocket - Socket wrapper that speaks the tor control protocol.
    |- ControlPort - Control connection via a port.
    |  |- get_address - provides the ip address of our socket
    |  +- get_port - provides the port of our socket
    |
    |- ControlSocketFile - Control connection via a local file socket.
    |  +- get_socket_path - provides the path of the socket we connect to
    |
    |- send - sends a message to the socket
    |- recv - receives a ControlMessage from the socket
    |- is_alive - reports if the socket is known to be closed
    |- connect - connects a new socket
    |- close - shuts down the socket
    +- __enter__ / __exit__ - manages socket connection
  
  send_message - Writes a message to a control socket.
  recv_message - Reads a ControlMessage from a control socket.
  send_formatting - Performs the formatting expected from sent messages.
  
  ControllerError - Base exception raised when using the controller.
    |- ProtocolError - Malformed socket data.
    |- OperationFailed - Tor was unable to successfully complete the operation.
    |  |- UnsatisfiableRequest - Tor was unable to satisfy a valid request.
    |  +- InvalidRequest - Invalid request.
    |     +- InvalidArguments - Invalid request parameters.
    +- SocketError - Communication with the socket failed.
       +- SocketClosed - Socket has been shut down.
"""

from __future__ import with_statement
from __future__ import absolute_import

import re
import socket
import threading

import stem.response
import stem.util.enum
import stem.util.log as log

class ControlSocket(object):
  """
  Wrapper for a socket connection that speaks the Tor control protocol. To the
  better part this transparently handles the formatting for sending and
  receiving complete messages. All methods are thread safe.
  
  Callers should not instantiate this class directly, but rather use subclasses
  which are expected to implement the **_make_socket()** method.
  """
  
  def __init__(self):
    self._socket, self._socket_file = None, None
    self._is_alive = False
    
    # Tracks sending and receiving separately. This should be safe, and doing
    # so prevents deadlock where we block writes because we're waiting to read
    # a message that isn't coming.
    
    self._send_lock = threading.RLock()
    self._recv_lock = threading.RLock()
  
  def send(self, message, raw = False):
    """
    Formats and sends a message to the control socket. For more information see
    the :func:`~stem.socket.send_message` function.
    
    :param str message: message to be formatted and sent to the socket
    :param bool raw: leaves the message formatting untouched, passing it to the socket as-is
    
    :raises:
      * :class:`stem.socket.SocketError` if a problem arises in using the socket
      * :class:`stem.socket.SocketClosed` if the socket is known to be shut down
    """
    
    with self._send_lock:
      try:
        if not self.is_alive(): raise SocketClosed()
        send_message(self._socket_file, message, raw)
      except SocketClosed, exc:
        # if send_message raises a SocketClosed then we should properly shut
        # everything down
        if self.is_alive(): self.close()
        raise exc
  
  def recv(self):
    """
    Receives a message from the control socket, blocking until we've received
    one. For more information see the :func:`~stem.socket.recv_message` function.
    
    :returns: :class:`~stem.response.ControlMessage` for the message received
    
    :raises:
      * :class:`stem.socket.ProtocolError` the content from the socket is malformed
      * :class:`stem.socket.SocketClosed` if the socket closes before we receive a complete message
    """
    
    with self._recv_lock:
      try:
        # makes a temporary reference to the _socket_file because connect()
        # and close() may set or unset it
        
        socket_file = self._socket_file
        
        if not socket_file: raise SocketClosed()
        return recv_message(socket_file)
      except SocketClosed, exc:
        # If recv_message raises a SocketClosed then we should properly shut
        # everything down. However, there's a couple cases where this will
        # cause deadlock...
        #
        # * this socketClosed was *caused by* a close() call, which is joining
        #   on our thread
        #
        # * a send() call that's currently in flight is about to call close(),
        #   also attempting to join on us
        #
        # To resolve this we make a non-blocking call to acquire the send lock.
        # If we get it then great, we can close safely. If not then one of the
        # above are in progress and we leave the close to them.
        
        if self.is_alive():
          if self._send_lock.acquire(False):
            self.close()
            self._send_lock.release()
        
        raise exc
  
  def is_alive(self):
    """
    Checks if the socket is known to be closed. We won't be aware if it is
    until we either use it or have explicitily shut it down.
    
    In practice a socket derived from a port knows about its disconnection
    after a failed :func:`~stem.socket.ControlSocket.recv` call. Socket file
    derived connections know after either a
    :func:`~stem.socket.ControlSocket.send` or
    :func:`~stem.socket.ControlSocket.recv`.
    
    This means that to have reliable detection for when we're disconnected
    you need to continually pull from the socket (which is part of what the
    :class:`~stem.control.BaseController` does).
    
    :returns: bool that's True if we're known to be shut down and False otherwise
    """
    
    return self._is_alive
  
  def connect(self):
    """
    Connects to a new socket, closing our previous one if we're already
    attached.
    
    :raises: :class:`stem.socket.SocketError` if unable to make a socket
    """
    
    with self._send_lock:
      # Closes the socket if we're currently attached to one. Once we're no
      # longer alive it'll be safe to acquire the recv lock because recv()
      # calls no longer block (raising SocketClosed instead).
      
      if self.is_alive(): self.close()
      
      with self._recv_lock:
        self._socket = self._make_socket()
        self._socket_file = self._socket.makefile()
        self._is_alive = True
        
        # It's possible for this to have a transient failure...
        # SocketError: [Errno 4] Interrupted system call
        #
        # It's safe to retry, so give it another try if it fails.
        
        try:
          self._connect()
        except SocketError:
          self._connect() # single retry
  
  def close(self):
    """
    Shuts down the socket. If it's already closed then this is a no-op.
    """
    
    with self._send_lock:
      # Function is idempotent with one exception: we notify _close() if this
      # is causing our is_alive() state to change.
      
      is_change = self.is_alive()
      
      if self._socket:
        # if we haven't yet established a connection then this raises an error
        # socket.error: [Errno 107] Transport endpoint is not connected
        
        try: self._socket.shutdown(socket.SHUT_RDWR)
        except socket.error: pass
        
        # Suppressing unexpected exceptions from close. For instance, if the
        # socket's file has already been closed then with python 2.7 that raises
        # with...
        # error: [Errno 32] Broken pipe
        
        try: self._socket.close()
        except: pass
      
      if self._socket_file:
        try: self._socket_file.close()
        except: pass
      
      self._socket = None
      self._socket_file = None
      self._is_alive = False
      
      if is_change:
        self._close()
  
  def _get_send_lock(self):
    """
    The send lock is useful to classes that interact with us at a deep level
    because it's used to lock :func:`stem.socket.ControlSocket.connect` /
    :func:`stem.socket.ControlSocket.close`, and by extension our
    :func:`stem.socket.ControlSocket.is_alive` state changes.
    
    :returns: **threading.RLock** that governs sending messages to our socket
      and state changes
    """
    
    return self._send_lock
  
  def __enter__(self):
    return self
  
  def __exit__(self, exit_type, value, traceback):
    self.close()
  
  def _connect(self):
    """
    Connection callback that can be overwritten by subclasses and wrappers.
    """
    
    pass
  
  def _close(self):
    """
    Disconnection callback that can be overwritten by subclasses and wrappers.
    """
    
    pass
  
  def _make_socket(self):
    """
    Constructs and connects new socket. This is implemented by subclasses.
    
    :returns: **socket.socket** for our configuration
    
    :raises:
      * :class:`stem.socket.SocketError` if unable to make a socket
      * **NotImplementedError** if not implemented by a subclass
    """
    
    raise NotImplementedError("Unsupported Operation: this should be implemented by the ControlSocket subclass")

class ControlPort(ControlSocket):
  """
  Control connection to tor. For more information see tor's ControlPort torrc
  option.
  """
  
  def __init__(self, control_addr = "127.0.0.1", control_port = 9051, connect = True):
    """
    ControlPort constructor.
    
    :param str control_addr: ip address of the controller
    :param int control_port: port number of the controller
    :param bool connect: connects to the socket if True, leaves it unconnected otherwise
    
    :raises: :class:`stem.socket.SocketError` if connect is **True** and we're
      unable to establish a connection
    """
    
    super(ControlPort, self).__init__()
    self._control_addr = control_addr
    self._control_port = control_port
    
    if connect: self.connect()
  
  def get_address(self):
    """
    Provides the ip address our socket connects to.
    
    :returns: str with the ip address of our socket
    """
    
    return self._control_addr
  
  def get_port(self):
    """
    Provides the port our socket connects to.
    
    :returns: int with the port of our socket
    """
    
    return self._control_port
  
  def _make_socket(self):
    try:
      control_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      control_socket.connect((self._control_addr, self._control_port))
      return control_socket
    except socket.error, exc:
      raise SocketError(exc)

class ControlSocketFile(ControlSocket):
  """
  Control connection to tor. For more information see tor's ControlSocket torrc
  option.
  """
  
  def __init__(self, socket_path = "/var/run/tor/control", connect = True):
    """
    ControlSocketFile constructor.
    
    :param str socket_path: path where the control socket is located
    :param bool connect: connects to the socket if True, leaves it unconnected otherwise
    
    :raises: :class:`stem.socket.SocketError` if connect is **True** and we're
      unable to establish a connection
    """
    
    super(ControlSocketFile, self).__init__()
    self._socket_path = socket_path
    
    if connect: self.connect()
  
  def get_socket_path(self):
    """
    Provides the path our socket connects to.
    
    :returns: str with the path for our control socket
    """
    
    return self._socket_path
  
  def _make_socket(self):
    try:
      control_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
      control_socket.connect(self._socket_path)
      return control_socket
    except socket.error, exc:
      raise SocketError(exc)

def send_message(control_file, message, raw = False):
  """
  Sends a message to the control socket, adding the expected formatting for
  single verses multi-line messages. Neither message type should contain an
  ending newline (if so it'll be treated as a multi-line message with a blank
  line at the end). If the message doesn't contain a newline then it's sent
  as...
  
  ::
  
    <message>\\r\\n
    
  and if it does contain newlines then it's split on ``\\n`` and sent as...
  
  ::
  
    +<line 1>\\r\\n
    <line 2>\\r\\n
    <line 3>\\r\\n
    .\\r\\n
  
  :param file control_file: file derived from the control socket (see the
    socket's makefile() method for more information)
  :param str message: message to be sent on the control socket
  :param bool raw: leaves the message formatting untouched, passing it to the
    socket as-is
  
  :raises:
    * :class:`stem.socket.SocketError` if a problem arises in using the socket
    * :class:`stem.socket.SocketClosed` if the socket is known to be shut down
  """
  
  if not raw: message = send_formatting(message)
  
  try:
    control_file.write(message)
    control_file.flush()
    
    log_message = message.replace("\r\n", "\n").rstrip()
    log.trace("Sent to tor:\n" + log_message)
  except socket.error, exc:
    log.info("Failed to send message: %s" % exc)
    
    # When sending there doesn't seem to be a reliable method for
    # distinguishing between failures from a disconnect verses other things.
    # Just accounting for known disconnection responses.
    
    if str(exc) == "[Errno 32] Broken pipe":
      raise SocketClosed(exc)
    else:
      raise SocketError(exc)
  except AttributeError:
    # if the control_file has been closed then flush will receive:
    # AttributeError: 'NoneType' object has no attribute 'sendall'
    
    log.info("Failed to send message: file has been closed")
    raise SocketClosed("file has been closed")

def recv_message(control_file):
  """
  Pulls from a control socket until we either have a complete message or
  encounter a problem.
  
  :param file control_file: file derived from the control socket (see the
    socket's makefile() method for more information)
  
  :returns: :class:`~stem.response.ControlMessage` read from the socket
  
  :raises:
    * :class:`stem.socket.ProtocolError` the content from the socket is malformed
    * :class:`stem.socket.SocketClosed` if the socket closes before we receive
      a complete message
  """
  
  parsed_content, raw_content = [], ""
  logging_prefix = "Error while receiving a control message (%s): "
  
  while True:
    try: line = control_file.readline()
    except AttributeError:
      # if the control_file has been closed then we will receive:
      # AttributeError: 'NoneType' object has no attribute 'recv'
      
      prefix = logging_prefix % "SocketClosed"
      log.info(prefix + "socket file has been closed")
      raise SocketClosed("socket file has been closed")
    except socket.error, exc:
      # when disconnected we get...
      # socket.error: [Errno 107] Transport endpoint is not connected
      
      prefix = logging_prefix % "SocketClosed"
      log.info(prefix + "received exception \"%s\"" % exc)
      raise SocketClosed(exc)
    
    raw_content += line
    
    # Parses the tor control lines. These are of the form...
    # <status code><divider><content>\r\n
    
    if len(line) == 0:
      # if the socket is disconnected then the readline() method will provide
      # empty content
      
      prefix = logging_prefix % "SocketClosed"
      log.info(prefix + "empty socket content")
      raise SocketClosed("Received empty socket content.")
    elif len(line) < 4:
      prefix = logging_prefix % "ProtocolError"
      log.info(prefix + "line too short, \"%s\"" % log.escape(line))
      raise ProtocolError("Badly formatted reply line: too short")
    elif not re.match(r'^[a-zA-Z0-9]{3}[-+ ]', line):
      prefix = logging_prefix % "ProtocolError"
      log.info(prefix + "malformed status code/divider, \"%s\"" % log.escape(line))
      raise ProtocolError("Badly formatted reply line: beginning is malformed")
    elif not line.endswith("\r\n"):
      prefix = logging_prefix % "ProtocolError"
      log.info(prefix + "no CRLF linebreak, \"%s\"" % log.escape(line))
      raise ProtocolError("All lines should end with CRLF")
    
    line = line[:-2] # strips off the CRLF
    status_code, divider, content = line[:3], line[3], line[4:]
    
    if divider == "-":
      # mid-reply line, keep pulling for more content
      parsed_content.append((status_code, divider, content))
    elif divider == " ":
      # end of the message, return the message
      parsed_content.append((status_code, divider, content))
      
      log_message = raw_content.replace("\r\n", "\n").rstrip()
      log.trace("Received from tor:\n" + log_message)
      
      return stem.response.ControlMessage(parsed_content, raw_content)
    elif divider == "+":
      # data entry, all of the following lines belong to the content until we
      # get a line with just a period
      
      while True:
        try: line = control_file.readline()
        except socket.error, exc:
          prefix = logging_prefix % "SocketClosed"
          log.info(prefix + "received an exception while mid-way through a data reply (exception: \"%s\", read content: \"%s\")" % (exc, log.escape(raw_content)))
          raise SocketClosed(exc)
        
        raw_content += line
        
        if not line.endswith("\r\n"):
          prefix = logging_prefix % "ProtocolError"
          log.info(prefix + "CRLF linebreaks missing from a data reply, \"%s\"" % log.escape(raw_content))
          raise ProtocolError("All lines should end with CRLF")
        elif line == ".\r\n":
          break # data block termination
        
        line = line[:-2] # strips off the CRLF
        
        # lines starting with a period are escaped by a second period (as per
        # section 2.4 of the control-spec)
        if line.startswith(".."): line = line[1:]
        
        # appends to previous content, using a newline rather than CRLF
        # separator (more conventional for multi-line string content outside
        # the windows world)
        
        content += "\n" + line
      
      parsed_content.append((status_code, divider, content))
    else:
      # this should never be reached due to the prefix regex, but might as well
      # be safe...
      prefix = logging_prefix % "ProtocolError"
      log.warn(prefix + "\"%s\" isn't a recognized divider type" % line)
      raise ProtocolError("Unrecognized divider type '%s': %s" % (divider, line))

def send_formatting(message):
  """
  Performs the formatting expected from sent control messages. For more
  information see the :func:`~stem.socket.send_message` function.
  
  :param str message: message to be formatted
  
  :returns: **str** of the message wrapped by the formatting expected from
    controllers
  """
  
  # From control-spec section 2.2...
  #   Command = Keyword OptArguments CRLF / "+" Keyword OptArguments CRLF CmdData
  #   Keyword = 1*ALPHA
  #   OptArguments = [ SP *(SP / VCHAR) ]
  #
  # A command is either a single line containing a Keyword and arguments, or a
  # multiline command whose initial keyword begins with +, and whose data
  # section ends with a single "." on a line of its own.
  
  # if we already have \r\n entries then standardize on \n to start with
  message = message.replace("\r\n", "\n")
  
  if "\n" in message:
    return "+%s\r\n.\r\n" % message.replace("\n", "\r\n")
  else:
    return message + "\r\n"

class ControllerError(Exception):
  "Base error for controller communication issues."

class ProtocolError(ControllerError):
  "Malformed content from the control socket."

class OperationFailed(ControllerError):
  """
  Base exception class for failed operations that return an error code
  
  :var str code: error code returned by Tor
  :var str message: error message returned by Tor or a human readable error
    message
  """
  
  def __init__(self, code = None, message = None):
    super(ControllerError, self).__init__(message)
    self.code = code
    self.message = message

class UnsatisfiableRequest(OperationFailed):
  """
  Exception raised if Tor was unable to process our request.
  """

class InvalidRequest(OperationFailed):
  """
  Exception raised when the request was invalid or malformed.
  """

class InvalidArguments(InvalidRequest):
  """
  Exception class for requests which had invalid arguments.
  
  :var str code: error code returned by Tor
  :var str message: error message returned by Tor or a human readable error
    message
  :var list arguments: a list of arguments which were invalid
  """
  
  def __init__(self, code = None, message = None, arguments = None):
    super(InvalidArguments, self).__init__(code, message)
    self.arguments = arguments

class SocketError(ControllerError):
  "Error arose while communicating with the control socket."

class SocketClosed(SocketError):
  "Control socket was closed before completing the message."

