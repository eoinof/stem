"""
Representation of tor exit policies. These can be easily used to check if
exiting to a destination is permissible or not. For instance...

::

  >>> from stem.exit_policy import ExitPolicy, MicrodescriptorExitPolicy
  >>> policy = ExitPolicy("accept *:80", "accept *:443", "reject *:*")
  >>> print policy
  accept *:80, accept *:443, reject *:*
  >>> print policy.summary()
  accept 80, 443
  >>> policy.can_exit_to("75.119.206.243", 80)
  True
  
  >>> policy = MicrodescriptorExitPolicy("accept 80,443")
  >>> print policy
  accept 80,443
  >>> policy.can_exit_to("75.119.206.243", 80)
  True

::

  ExitPolicy - Exit policy for a Tor relay
    |  + MicrodescriptorExitPolicy - Microdescriptor exit policy
    |- set_default_allowed - sets the can_exit_to response when no rules match
    |- can_exit_to - check if exiting to this destination is allowed or not
    |- is_exiting_allowed - check if any exiting is allowed
    |- summary - provides a short label, similar to a microdescriptor
    |- __str__  - string representation
    +- __iter__ - ExitPolicyRule entries that this contains
  
  ExitPolicyRule - Single rule of an exit policy chain
    |- is_address_wildcard - checks if we'll accept any address
    |- is_port_wildcard - checks if we'll accept any port
    |- is_match - checks if we match a given destination
    +- __str__ - string representation for this rule
  
  AddressType - Enumerations for IP address types that can be in an exit policy
    |- WILDCARD - any address of either IPv4 or IPv6
    |- IPv4 - IPv4 address
    +- IPv6 - IPv6 address
"""

import stem.util.connection
import stem.util.enum

AddressType = stem.util.enum.Enum(("WILDCARD", "Wildcard"), ("IPv4", "IPv4"), ("IPv6", "IPv6"))

# TODO: The ExitPolicyRule's exitpatterns are used everywhere except the torrc.
# This is fine for now, but we should add a subclass to handle those slight
# differences later if we want to provide the ability to parse torrcs.

# TODO: The ExitPolicyRule could easily be a mutable class if we did the
# following...
#
# * Provided setter methods that acquired an RLock which also wrapped all of
#   our current methods to provide thread safety.
#
# * Reset our derived attributes (self._addr_bin, self._mask_bin, and
#   self._str_representation) when we changed something that it was based on.
#
# That said, I'm not sure if this is entirely desirable since for most use
# cases we *want* the caller to have an immutable ExitPolicy (since it
# reflects something they... well, can't modify). However, I can think of
# some use cases where we might want to construct custom policies. Maybe make
# it a CustomExitPolicyRule subclass?

class ExitPolicy(object):
  """
  Policy for the destinations that a relay allows or denies exiting to. This
  is, in effect, just a list of :class:`~stem.exit_policy.ExitPolicyRule`
  entries.
  
  :param list rules: **str** or :class:`~stem.exit_policy.ExitPolicyRule`
    entries that make up this policy
  """
  
  def __init__(self, *rules):
    self._rules = []
    
    for rule in rules:
      if isinstance(rule, str):
        self._rules.append(ExitPolicyRule(rule.strip()))
      elif isinstance(rule, ExitPolicyRule):
        self._rules.append(rule)
      else:
        raise TypeError("Exit policy rules can only contain strings or ExitPolicyRules, got a %s (%s)" % (type(rule), rules))
    
    self._is_allowed_default = True
    self._summary_representation = None
  
  def set_default_allowed(self, is_allowed_default):
    """
    Generally policies end with either an 'reject \*:\*' or 'accept \*:\*'
    policy, but if it doesn't then is_allowed_default will determine the
    default response for our :meth:`~stem.exit_policy.ExitPolicy.can_exit_to`
    method.
    
    Our default, and tor's, is **True**.
    
    :param bool is_allowed_default:
      :meth:`~stem.exit_policy.ExitPolicy.can_exit_to` default when no rules
      apply
    """
    
    self._is_allowed_default = is_allowed_default
  
  def can_exit_to(self, address = None, port = None):
    """
    Checks if this policy allows exiting to a given destination or not. If the
    address or port is omitted then this will check if we allow for its
    wildcard.
    
    :param str address: IPv4 or IPv6 address (with or without brackets)
    :param int port: port number
    
    :returns: **True** if exiting to this destination is allowed, **False** otherwise
    """
    
    for rule in self._rules:
      if rule.is_match(address, port):
        return rule.is_accept
    
    return self._is_allowed_default
  
  def is_exiting_allowed(self):
    """
    Provides **True** if the policy allows exiting whatsoever, **False**
    otherwise.
    """
    
    rejected_ports = set()
    for rule in self._rules:
      if rule.is_accept:
        for port in xrange(rule.min_port, rule.max_port + 1):
          if not port in rejected_ports:
            return True
      elif rule.is_address_wildcard():
        if rule.is_port_wildcard():
          return False
        else:
          rejected_ports.update(range(rule.min_port, rule.max_port + 1))
    
    return self._is_allowed_default
  
  def summary(self):
    """
    Provides a short description of our policy chain, similar to a
    microdescriptor. This excludes entries that don't cover all IP
    addresses, and is either white-list or blacklist policy based on
    the final entry. For instance...
    
    ::
    
      >>> policy = ExitPolicy('accept *:80', 'accept *:443', 'reject *:*')
      >>> policy.summary()
      "accept 80, 443"
      
      >>> policy = ExitPolicy('accept *:443', 'reject *:1-1024', 'accept *:*')
      >>> policy.summary()
      "reject 1-442, 444-1024"
    
    :returns: **str** with a concise summary for our policy
    """
    
    if self._summary_representation is None:
      # determines if we're a white-list or blacklist
      is_whitelist = not self._is_allowed_default
      
      for rule in self._rules:
        if rule.is_address_wildcard() and rule.is_port_wildcard():
          is_whitelist = not rule.is_accept
          break
      
      # Iterates over the policies and adds the the ports we'll return (ie,
      # allows if a white-list and rejects if a blacklist). Regardless of a
      # port's allow/reject policy, all further entries with that port are
      # ignored since policies respect the first matching policy.
      
      display_ports, skip_ports = [], set()
      
      for rule in self._rules:
        if not rule.is_address_wildcard(): continue
        elif rule.is_port_wildcard(): break
        
        for port in xrange(rule.min_port, rule.max_port + 1):
          if port in skip_ports: continue
          
          # if accept + white-list or reject + blacklist then add
          if rule.is_accept == is_whitelist:
            display_ports.append(port)
          
          # all further entries with this port should be ignored
          skip_ports.add(port)
      
      # convert port list to a list of ranges (ie, ['1-3'] rather than [1, 2, 3])
      if display_ports:
        display_ranges, temp_range = [], []
        display_ports.sort()
        display_ports.append(None) # ending item to include last range in loop
        
        for port in display_ports:
          if not temp_range or temp_range[-1] + 1 == port:
            temp_range.append(port)
          else:
            if len(temp_range) > 1:
              display_ranges.append("%i-%i" % (temp_range[0], temp_range[-1]))
            else:
              display_ranges.append(str(temp_range[0]))
              
            temp_range = [port]
      else:
        # everything for the inverse
        is_whitelist = not is_whitelist
        display_ranges = ["1-65535"]
      
      # constructs the summary string
      label_prefix = "accept " if is_whitelist else "reject "
      
      self._summary_representation = (label_prefix + ", ".join(display_ranges)).strip()
    
    return self._summary_representation
  
  def __iter__(self):
    for rule in self._rules:
      yield rule
  
  def __str__(self):
    return ', '.join([str(rule) for rule in self._rules])
  
  def __eq__(self, other):
    if isinstance(other, ExitPolicy):
      return self._rules == list(other)
    else:
      return False

class MicrodescriptorExitPolicy(ExitPolicy):
  """
  Exit policy provided by the microdescriptors. This is a distilled version of
  a normal :class:`~stem.exit_policy.ExitPolicy` contains, just consisting of a
  list of ports that are either accepted or rejected. For instance...
  
  ::
  
    accept 80,443       # only accepts common http ports
    reject 1-1024       # only accepts non-privileged ports
  
  Since these policies are a subset of the exit policy information (lacking IP
  ranges) clients can only use them to guess if a relay will accept traffic or
  not. To quote the `dir-spec <https://gitweb.torproject.org/torspec.git/blob/HEAD:/dir-spec.txt>`_ (section 3.2.1)...
  
  ::
  
    With microdescriptors, clients don't learn exact exit policies:
    clients can only guess whether a relay accepts their request, try the
    BEGIN request, and might get end-reason-exit-policy if they guessed
    wrong, in which case they'll have to try elsewhere.
  
  :var set ports: ports that this policy includes
  :var bool is_accept: **True** if these are ports that we accept, **False** if
    they're ports that we reject
  
  :param str policy: policy string that describes this policy
  """
  
  def __init__(self, policy):
    # Microdescriptor policies are of the form...
    #
    #   MicrodescriptrPolicy ::= ("accept" / "reject") SP PortList NL
    #   PortList ::= PortOrRange
    #   PortList ::= PortList "," PortOrRange
    #   PortOrRange ::= INT "-" INT / INT
    
    self.ports = set()
    self._policy = policy
    
    if policy.startswith("accept"):
      self.is_accept = True
    elif policy.startswith("reject"):
      self.is_accept = False
    else:
      raise ValueError("A microdescriptor exit policy must start with either 'accept' or 'reject': %s" % policy)
    
    policy = policy[6:]
    
    if not policy.startswith(" ") or (len(policy) - 1 != len(policy.lstrip())):
      raise ValueError("A microdescriptor exit policy should have a space separating accept/reject from its port list: %s" % self._policy)
    
    policy = policy[1:]
    
    # convert our port list into ExitPolicyRules
    rules = []
    rule_format = "accept *:%s" if self.is_accept else "reject *:%s"
    
    for port_entry in policy.split(","):
      rule_str = rule_format % port_entry
      
      try:
        rule = ExitPolicyRule(rule_str)
        self.ports.update(range(rule.min_port, rule.max_port + 1))
        rules.append(rule)
      except ValueError, exc:
        exc_msg = "Policy '%s' is malformed. %s" % (self._policy, str(exc).replace(rule_str, port_entry))
        raise ValueError(exc_msg)
    
    super(MicrodescriptorExitPolicy, self).__init__(*rules)
  
  def can_exit_to(self, address = None, port = None):
    # we can greatly simplify our check since our policies don't concern
    # addresses or masks
    
    if port in self.ports:
      return self.is_accept
    else:
      return not self.is_accept
  
  def __str__(self):
    return self._policy
  
  def __eq__(self, other):
    if isinstance(other, MicrodescriptorExitPolicy):
      return str(self) == str(other)
    else:
      return False

class ExitPolicyRule(object):
  """
  Single rule from the user's exit policy. These rules are chained together to
  form complete policies that describe where a relay will and will not allow
  traffic to exit.
  
  The format of these rules are formally described in the `dir-spec
  <https://gitweb.torproject.org/torspec.git/blob/HEAD:/dir-spec.txt>`_ as an
  "exitpattern". Note that while these are similar to tor's man page entry for
  ExitPolicies, it's not the exact same. An exitpattern is better defined and
  stricter in what it'll accept. For instance, ports are not optional and it
  does not contain the 'private' alias.
  
  This should be treated as an immutable object.
  
  :var str rule: rule that we were originally created from
  :var bool is_accept: indicates if exiting is allowed or disallowed
  
  :var AddressType address_type: type of address that we have
  :var str address: address that this rule is for
  :var str mask: subnet mask for the address (ex. "255.255.255.0")
  :var int masked_bits: number of bits the subnet mask represents, **None** if
    the mask can't have a bit representation
  
  :var int min_port: lower end of the port range that we include (inclusive)
  :var int max_port: upper end of the port range that we include (inclusive)
  
  :param str rule: exit policy rule to be parsed
  
  :raises: **ValueError** if input isn't a valid tor exit policy rule
  """
  
  def __init__(self, rule):
    self.rule = rule
    
    # policy ::= "accept" exitpattern | "reject" exitpattern
    # exitpattern ::= addrspec ":" portspec
    
    if rule.startswith("accept"):
      self.is_accept = True
    elif rule.startswith("reject"):
      self.is_accept = False
    else:
      raise ValueError("An exit policy must start with either 'accept' or 'reject': %s" % rule)
    
    exitpattern = rule[6:]
    
    if not exitpattern.startswith(" ") or (len(exitpattern) - 1 != len(exitpattern.lstrip())):
      raise ValueError("An exit policy should have a space separating its accept/reject from the exit pattern: %s" % rule)
    
    exitpattern = exitpattern[1:]
    
    if not ":" in exitpattern:
      raise ValueError("An exitpattern must be of the form 'addrspec:portspec': %s" % rule)
    
    self.address = None
    self.address_type = None
    self.mask = self.masked_bits = None
    self.min_port = self.max_port = None
    
    addrspec, portspec = exitpattern.rsplit(":", 1)
    self._apply_addrspec(addrspec)
    self._apply_portspec(portspec)
    
    # Pre-calculating the integer representation of our mask and masked
    # address. These are used by our is_match() method to compare ourselves to
    # other addresses.
    
    if self.is_address_wildcard():
      # is_match() will short circuit so these are unused
      self._mask_bin = self._addr_bin = None
    else:
      self._mask_bin = int(stem.util.connection.get_address_binary(self.mask), 2)
      self._addr_bin = int(stem.util.connection.get_address_binary(self.address), 2) & self._mask_bin
    
    self._str_representation = None
  
  def is_address_wildcard(self):
    """
    **True** if we'll match against any address, **False** otherwise. Note that
    this may be different from matching against a /0 because policies can
    contain both IPv4 and IPv6 addresses (so 0.0.0.0/0 won't match against an
    IPv6 address).
    
    :returns: **bool** for if our address matching is a wildcard
    """
    
    return self.address_type == AddressType.WILDCARD
  
  def is_port_wildcard(self):
    """
    **True** if we'll match against any port, **False** otherwise.
    
    :returns: **bool** for if our port matching is a wildcard
    """
    
    return self.min_port in (0, 1) and self.max_port == 65535
  
  def is_match(self, address = None, port = None):
    """
    **True** if we match against the given destination, **False** otherwise. If
    the address or port is omitted then that'll only match against a wildcard.
    
    :param str address: IPv4 or IPv6 address (with or without brackets)
    :param int port: port number
    
    :returns: **bool** indicating if we match against this destination
    
    :raises: **ValueError** if provided with a malformed address or port
    """
    
    # validate our input and check if the argument doesn't match our address type
    if address != None:
      if stem.util.connection.is_valid_ip_address(address):
        if self.address_type == AddressType.IPv6: return False
      elif stem.util.connection.is_valid_ipv6_address(address, allow_brackets = True):
        if self.address_type == AddressType.IPv4: return False
        
        address = address.lstrip("[").rstrip("]")
      else:
        raise ValueError("'%s' isn't a valid IPv4 or IPv6 address" % address)
    
    if port != None and not stem.util.connection.is_valid_port(port):
      raise ValueError("'%s' isn't a valid port" % port)
    
    if not self.is_address_wildcard():
      # Already got the integer representation of our mask and our address
      # with the mask applied. Just need to check if this address with the
      # mask applied matches.
      
      if address is None:
        return False
      else:
        comparison_addr_bin = int(stem.util.connection.get_address_binary(address), 2)
        comparison_addr_bin &= self._mask_bin
        if self._addr_bin != comparison_addr_bin: return False
    
    if not self.is_port_wildcard():
      if port is None:
        return False
      elif port < self.min_port or port > self.max_port:
        return False
    
    return True
  
  def __str__(self):
    """
    Provides the string representation of our policy. This does not
    necessarily match the rule that we were constructed from (due to things
    like IPv6 address collapsing or the multiple representations that our mask
    can have). However, it is a valid rule that would be accepted by our
    constructor to re-create this rule.
    """
    
    if self._str_representation is None:
      label = "accept " if self.is_accept else "reject "
      
      if self.is_address_wildcard():
        label += "*:"
      else:
        if self.address_type == AddressType.IPv4:
          label += self.address
        else:
          label += "[%s]" % self.address
        
        # Including our mask label as follows...
        # - exclude our mask if it doesn't do anything
        # - use our masked bit count if we can
        # - use the mask itself otherwise
        
        if self.mask in (stem.util.connection.FULL_IPv4_MASK, stem.util.connection.FULL_IPv6_MASK):
          label += ":"
        elif not self.masked_bits is None:
          label += "/%i:" % self.masked_bits
        else:
          label += "/%s:" % self.mask
      
      if self.is_port_wildcard():
        label += "*"
      elif self.min_port == self.max_port:
        label += str(self.min_port)
      else:
        label += "%i-%i" % (self.min_port, self.max_port)
      
      self._str_representation = label
    
    return self._str_representation
  
  def _apply_addrspec(self, addrspec):
    # Parses the addrspec...
    # addrspec ::= "*" | ip4spec | ip6spec
    
    if "/" in addrspec:
      self.address, addr_extra = addrspec.split("/", 1)
    else:
      self.address, addr_extra = addrspec, None
    
    if addrspec == "*":
      self.address_type = AddressType.WILDCARD
      self.address = self.mask = self.masked_bits = None
    elif stem.util.connection.is_valid_ip_address(self.address):
      # ipv4spec ::= ip4 | ip4 "/" num_ip4_bits | ip4 "/" ip4mask
      # ip4 ::= an IPv4 address in dotted-quad format
      # ip4mask ::= an IPv4 mask in dotted-quad format
      # num_ip4_bits ::= an integer between 0 and 32
      
      self.address_type = AddressType.IPv4
      
      if addr_extra is None:
        self.mask = stem.util.connection.FULL_IPv4_MASK
        self.masked_bits = 32
      elif stem.util.connection.is_valid_ip_address(addr_extra):
        # provided with an ip4mask
        self.mask = addr_extra
        
        try:
          self.masked_bits = stem.util.connection.get_masked_bits(addr_extra)
        except ValueError:
          # mask can't be represented as a number of bits (ex. "255.255.0.255")
          self.masked_bits = None
      elif addr_extra.isdigit():
        # provided with a num_ip4_bits
        self.mask = stem.util.connection.get_mask(int(addr_extra))
        self.masked_bits = int(addr_extra)
      else:
        raise ValueError("The '%s' isn't a mask nor number of bits: %s" % (addr_extra, self.rule))
    elif self.address.startswith("[") and self.address.endswith("]") and \
      stem.util.connection.is_valid_ipv6_address(self.address[1:-1]):
      # ip6spec ::= ip6 | ip6 "/" num_ip6_bits
      # ip6 ::= an IPv6 address, surrounded by square brackets.
      # num_ip6_bits ::= an integer between 0 and 128
      
      self.address = stem.util.connection.expand_ipv6_address(self.address[1:-1].upper())
      self.address_type = AddressType.IPv6
      
      if addr_extra is None:
        self.mask = stem.util.connection.FULL_IPv6_MASK
        self.masked_bits = 128
      elif addr_extra.isdigit():
        # provided with a num_ip6_bits
        self.mask = stem.util.connection.get_mask_ipv6(int(addr_extra))
        self.masked_bits = int(addr_extra)
      else:
        raise ValueError("The '%s' isn't a number of bits: %s" % (addr_extra, self.rule))
    else:
      raise ValueError("Address isn't a wildcard, IPv4, or IPv6 address: %s" % self.rule)
  
  def _apply_portspec(self, portspec):
    # Parses the portspec...
    # portspec ::= "*" | port | port "-" port
    # port ::= an integer between 1 and 65535, inclusive.
    #
    # Due to a tor bug the spec says that we should accept port of zero, but
    # connections to port zero are never permitted.
    
    if portspec == "*":
      self.min_port, self.max_port = 1, 65535
    elif portspec.isdigit():
      # provided with a single port
      if stem.util.connection.is_valid_port(portspec, allow_zero = True):
        self.min_port = self.max_port = int(portspec)
      else:
        raise ValueError("'%s' isn't within a valid port range: %s" % (portspec, self.rule))
    elif "-" in portspec:
      # provided with a port range
      port_comp = portspec.split("-", 1)
      
      if stem.util.connection.is_valid_port(port_comp, allow_zero = True):
        self.min_port = int(port_comp[0])
        self.max_port = int(port_comp[1])
        
        if self.min_port > self.max_port:
          raise ValueError("Port range has a lower bound that's greater than its upper bound: %s" % self.rule)
      else:
        raise ValueError("Malformed port range: %s" % self.rule)
    else:
      raise ValueError("Port value isn't a wildcard, integer, or range: %s" % self.rule)
  
  def __eq__(self, other):
    if isinstance(other, ExitPolicyRule):
      # Our string representation encompasses our effective policy. Technically
      # this isn't quite right since our rule attribute may differ (ie, "accept
      # 0.0.0.0/0" == "accept 0.0.0.0/0.0.0.0" will be True), but these
      # policies are effectively equivalent.
      
      return str(self) == str(other)
    else:
      return False

