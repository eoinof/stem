import stem.socket
import stem.response

class GetConfResponse(stem.response.ControlMessage):
  """
  Reply for a GETCONF query.
  
  Note that configuration parameters won't match what we queried for if it's one
  of the special mapping options (ex. "HiddenServiceOptions").
  
  :var dict entries: mapping between the config parameter (**str**) and their
    values (**list** of **str**)
  """
  
  def _parse_message(self):
    # Example:
    # 250-CookieAuthentication=0
    # 250-ControlPort=9100
    # 250-DataDirectory=/home/neena/.tor
    # 250 DirPort
    
    self.entries = {}
    remaining_lines = list(self)
    
    if self.content() == [("250", " ", "OK")]: return
    
    if not self.is_ok():
      unrecognized_keywords = []
      for code, _, line in self.content():
        if code == "552" and line.startswith("Unrecognized configuration key \"") and line.endswith("\""):
          unrecognized_keywords.append(line[32:-1])
      
      if unrecognized_keywords:
        raise stem.socket.InvalidArguments("552", "GETCONF request contained unrecognized keywords: %s" \
            % ', '.join(unrecognized_keywords), unrecognized_keywords)
      else:
        raise stem.socket.ProtocolError("GETCONF response contained a non-OK status code:\n%s" % self)
    
    while remaining_lines:
      line = remaining_lines.pop(0)
      
      if line.is_next_mapping(quoted = False):
        key, value = line.split("=", 1) # TODO: make this part of the ControlLine?
      elif line.is_next_mapping(quoted = True):
        # TODO: doesn't seem to occur yet in practice...
        # https://trac.torproject.org/6172
        
        key, value = line.pop_mapping(True).items()[0]
      else:
        key, value = (line.pop(), None)
      
      self.entries.setdefault(key, []).append(value)

