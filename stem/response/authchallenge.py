import binascii

import stem.socket
import stem.response
import stem.util.tor_tools

class AuthChallengeResponse(stem.response.ControlMessage):
  """
  AUTHCHALLENGE query response.
  
  :var str server_hash: server hash provided by tor
  :var str server_nonce: server nonce provided by tor
  """
  
  def _parse_message(self):
    # Example:
    #   250 AUTHCHALLENGE SERVERHASH=680A73C9836C4F557314EA1C4EDE54C285DB9DC89C83627401AEF9D7D27A95D5 SERVERNONCE=F8EA4B1F2C8B40EF1AF68860171605B910E3BBCABADF6FC3DB1FA064F4690E85
    
    self.server_hash = None
    self.server_nonce = None
    
    if not self.is_ok():
      raise stem.socket.ProtocolError("AUTHCHALLENGE response didn't have an OK status:\n%s" % self)
    elif len(self) > 1:
      raise stem.socket.ProtocolError("Received multiline AUTHCHALLENGE response:\n%s" % self)
    
    line = self[0]
    
    # sanity check that we're a AUTHCHALLENGE response
    if not line.pop() == "AUTHCHALLENGE":
      raise stem.socket.ProtocolError("Message is not an AUTHCHALLENGE response (%s)" % self)
    
    if line.is_next_mapping("SERVERHASH"):
      value = line.pop_mapping()[1]
      
      if not stem.util.tor_tools.is_hex_digits(value, 64):
        raise stem.socket.ProtocolError("SERVERHASH has an invalid value: %s" % value)
      
      self.server_hash = binascii.a2b_hex(value)
    else:
      raise stem.socket.ProtocolError("Missing SERVERHASH mapping: %s" % line)
    
    if line.is_next_mapping("SERVERNONCE"):
      value = line.pop_mapping()[1]
      
      if not stem.util.tor_tools.is_hex_digits(value, 64):
        raise stem.socket.ProtocolError("SERVERNONCE has an invalid value: %s" % value)
      
      self.server_nonce = binascii.a2b_hex(value)
    else:
      raise stem.socket.ProtocolError("Missing SERVERNONCE mapping: %s" % line)

