"""
Helper functions for creating mock objects and monkey patching to help with
testing. With python's builtin unit testing framework the setUp and test
functions set up mocking, which is then reverted in the tearDown method by
calling :func:`test.mocking.revert_mocking`.

::

  mock - replaces a function with an alternative implementation
  revert_mocking - reverts any changes made by the mock function
  get_real_function - provides the non-mocked version of a function
  get_all_combinations - provides all combinations of attributes
  support_with - makes object be compatible for use via the 'with' keyword
  get_object - get an arbitrary mock object of any class
  
  Mocking Functions
    no_op           - does nothing
    return_value    - returns a given value
    return_true     - returns True
    return_false    - returns False
    return_none     - returns None
    return_for_args - return based on the input arguments
    raise_exception - raises an exception when called
  
  Instance Constructors
    get_message                     - stem.socket.ControlMessage
    get_protocolinfo_response       - stem.response.protocolinfo.ProtocolInfoResponse
    
    stem.descriptor.server_descriptor
      get_relay_server_descriptor  - RelayDescriptor
      get_bridge_server_descriptor - BridgeDescriptor
    
    stem.descriptor.extrainfo_descriptor
      get_relay_extrainfo_descriptor  - RelayExtraInfoDescriptor
      get_bridge_extrainfo_descriptor - BridgeExtraInfoDescriptor
    
    stem.descriptor.networkstatus
      get_directory_authority        - DirectoryAuthority
      get_key_certificate            - KeyCertificate
      get_network_status_document_v2 - NetworkStatusDocumentV2
      get_network_status_document_v3 - NetworkStatusDocumentV3
    
    stem.descriptor.router_status_entry
      get_router_status_entry_v2       - RouterStatusEntryV2
      get_router_status_entry_v3       - RouterStatusEntryV3
      get_router_status_entry_micro_v3 - RouterStatusEntryMicroV3
"""

import inspect
import itertools
import StringIO
import __builtin__

import stem.response
import stem.socket
import stem.descriptor.server_descriptor
import stem.descriptor.extrainfo_descriptor
import stem.descriptor.networkstatus
import stem.descriptor.router_status_entry

# Once we've mocked a function we can't rely on its __module__ or __name__
# attributes, so instead we associate a unique 'mock_id' attribute that maps
# back to the original attributes.

MOCK_ID = itertools.count(0)

# mock_id => (module, function_name, original_function)

MOCK_STATE = {}

BUILTIN_TYPE = type(open)

CRYPTO_BLOB = """
MIGJAoGBAJv5IIWQ+WDWYUdyA/0L8qbIkEVH/cwryZWoIaPAzINfrw1WfNZGtBmg
skFtXhOHHqTRN4GPPrZsAIUOQGzQtGb66IQgT4tO/pj+P6QmSCCdTfhvGfgTCsC+
WPi4Fl2qryzTb3QO5r5x7T8OsG2IBUET1bLQzmtbC560SYR49IvVAgMBAAE=
"""

DOC_SIG = stem.descriptor.networkstatus.DocumentSignature(
  None,
  "14C131DFC5C6F93646BE72FA1401C02A8DF2E8B4",
  "BF112F1C6D5543CFD0A32215ACABD4197B5279AD",
  "-----BEGIN SIGNATURE-----%s-----END SIGNATURE-----" % CRYPTO_BLOB)


BRIDGE_SERVER_HEADER = (
  ("router", "Unnamed 10.45.227.253 9001 0 0"),
  ("router-digest", "006FD96BA35E7785A6A3B8B75FE2E2435A13BDB4"),
  ("published", "2012-03-22 17:34:38"),
  ("bandwidth", "409600 819200 5120"),
  ("reject", "*:*"),
)

RELAY_EXTRAINFO_HEADER = (
  ("extra-info", "ninja B2289C3EAB83ECD6EB916A2F481A02E6B76A0A48"),
  ("published", "2012-05-05 17:03:50"),
)

RELAY_EXTRAINFO_FOOTER = (
  ("router-signature", "\n-----BEGIN SIGNATURE-----%s-----END SIGNATURE-----" % CRYPTO_BLOB),
)

BRIDGE_EXTRAINFO_HEADER = (
  ("extra-info", "ec2bridgereaac65a3 1EC248422B57D9C0BD751892FE787585407479A4"),
  ("published", "2012-05-05 17:03:50"),
)

BRIDGE_EXTRAINFO_FOOTER = (
  ("router-digest", "006FD96BA35E7785A6A3B8B75FE2E2435A13BDB4"),
)

ROUTER_STATUS_ENTRY_V2_HEADER = (
  ("r", "caerSidi p1aag7VwarGxqctS7/fS0y5FU+s oQZFLYe9e4A7bOkWKR7TaNxb0JE 2012-08-06 11:19:31 71.35.150.29 9001 0"),
)

ROUTER_STATUS_ENTRY_V3_HEADER = (
  ("r", "caerSidi p1aag7VwarGxqctS7/fS0y5FU+s oQZFLYe9e4A7bOkWKR7TaNxb0JE 2012-08-06 11:19:31 71.35.150.29 9001 0"),
  ("s", "Fast Named Running Stable Valid"),
)

ROUTER_STATUS_ENTRY_MICRO_V3_HEADER = (
  ("r", "Konata ARIJF2zbqirB9IwsW0mQznccWww 2012-09-24 13:40:40 69.64.48.168 9001 9030"),
  ("m", "aiUklwBrua82obG5AsTX+iEpkjQA2+AQHxZ7GwMfY70"),
  ("s", "Fast Guard HSDir Named Running Stable V2Dir Valid"),
)

AUTHORITY_HEADER = (
  ("dir-source", "turtles 27B6B5996C426270A5C95488AA5BCEB6BCC86956 no.place.com 76.73.17.194 9030 9090"),
  ("contact", "Mike Perry <email>"),
)

KEY_CERTIFICATE_HEADER = (
  ("dir-key-certificate-version", "3"),
  ("fingerprint", "27B6B5996C426270A5C95488AA5BCEB6BCC86956"),
  ("dir-key-published", "2011-11-28 21:51:04"),
  ("dir-key-expires", "2012-11-28 21:51:04"),
  ("dir-identity-key", "\n-----BEGIN RSA PUBLIC KEY-----%s-----END RSA PUBLIC KEY-----" % CRYPTO_BLOB),
  ("dir-signing-key", "\n-----BEGIN RSA PUBLIC KEY-----%s-----END RSA PUBLIC KEY-----" % CRYPTO_BLOB),
)

KEY_CERTIFICATE_FOOTER = (
  ("dir-key-certification", "\n-----BEGIN SIGNATURE-----%s-----END SIGNATURE-----" % CRYPTO_BLOB),
)

NETWORK_STATUS_DOCUMENT_HEADER_V2 = (
  ("network-status-version", "2"),
  ("dir-source", "18.244.0.114 18.244.0.114 80"),
  ("fingerprint", "719BE45DE224B607C53707D0E2143E2D423E74CF"),
  ("contact", "arma at mit dot edu"),
  ("published", "2005-12-16 00:13:46"),
  ("dir-signing-key", "\n-----BEGIN RSA PUBLIC KEY-----%s-----END RSA PUBLIC KEY-----" % CRYPTO_BLOB),
)

NETWORK_STATUS_DOCUMENT_FOOTER_V2 = (
  ("directory-signature", "moria2\n-----BEGIN SIGNATURE-----%s-----END SIGNATURE-----" % CRYPTO_BLOB),
)

NETWORK_STATUS_DOCUMENT_HEADER = (
  ("network-status-version", "3"),
  ("vote-status", "consensus"),
  ("consensus-methods", None),
  ("consensus-method", None),
  ("published", None),
  ("valid-after", "2012-09-02 22:00:00"),
  ("fresh-until", "2012-09-02 22:00:00"),
  ("valid-until", "2012-09-02 22:00:00"),
  ("voting-delay", "300 300"),
  ("client-versions", None),
  ("server-versions", None),
  ("known-flags", "Authority BadExit Exit Fast Guard HSDir Named Running Stable Unnamed V2Dir Valid"),
  ("params", None),
)

NETWORK_STATUS_DOCUMENT_FOOTER = (
  ("directory-footer", ""),
  ("bandwidth-weights", None),
  ("directory-signature", "%s %s\n%s" % (DOC_SIG.identity, DOC_SIG.key_digest, DOC_SIG.signature)),
)

ACTUAL_SIGNATURE_BLOB = """
TayY8cGAeBhXPt5abYRdzdqG+lF8mDrbGTy7/qiOMRIjK44usO180rOJHv1JWFfv
bGoDkz0ThZclt4K+DoXpvsjnrdIWbAJ4ZkM7AIHnQQqdhD1tdV1QQGDmvASnZypo
rLlwqrcJqzqCd06a0ZouXdjAv+WUJUlaYE4obZggHbc=
"""

ACTUAL_ONION_BLOB = """
MIGJAoGBAN3rQ4J/K5dMA5Pw73FdllnBSXeu+6D1VCqFJBQRXlbrQbepreQ+DMB6
MNCHNJNjVhLczCEvUn3oPugwlEJ0ZRZzmrT1veOn6ZFCwk6j2aMqTfwFm+OPvVI+
ZAHoAlr89hQh3OCqM+UzuhZ5jGPSsjEFTanHWRbck8FKUOT7zpDBAgMBAAE=
"""

ACTUAL_SIGNING_BLOB = """
MIGJAoGBAKSeRJCARnpGGG555JpOPMlKEkDf6HUoPFTdAj8oSED6XVgyY/JAbB1M
+xwkCc2EPrJmH4VIWpg77si6N5AY9+a8gOxFtpwMJOtHAmJDfOUzZj3fABpolsDi
ZCyt6AjPlqIUJKLciDDdEoW6ZhvlSa/swPSK5SXM4AYfskqN6ExVAgMBAAE=
"""

ACTUAL_FINGERPRINT = "CA74 7C45 DB8E 305D 5AE7 26F9 E41D F7D3 661C 850B"

RELAY_SERVER_HEADER = (
  ("router", "rainbow 80.243.60.137 9001 0 9030"),
  ("platform", "Tor 0.1.0.14 on FreeBSD i386"),
  ("published", "2005-12-15 15:56:20"),
  ("opt", "fingerprint %s" % ACTUAL_FINGERPRINT),
  ("uptime", 87675),
  ("bandwidth", "30720 5242880 79028"),
  ("onion-key", "\n-----BEGIN RSA PUBLIC KEY-----%s-----END RSA PUBLIC KEY-----" % ACTUAL_ONION_BLOB),
  ("signing-key", "\n-----BEGIN RSA PUBLIC KEY-----%s-----END RSA PUBLIC KEY-----" % ACTUAL_SIGNING_BLOB),
  ("opt", "write-history 2005-12-15 15:49:53 (900 s) 13820,38428,1674359,9006016,11910920,14690648,19505931,15805563,18517886,14909063,12039102,11480366,8851774,14355228,8743624,6588812,9769600,6677425,6756297,3996460,3919828,4110913,5461893,4711272,6373048,6261073,5355765,3152434,7864095,7564967,7857187,3598081,8075058,5363328,6526001,8334202,8002262,5170610,5875803,4605448,5010254,4481500,4073617,5187712,3641863,2508318,3440460,4315865,3872467,3886329,6036034,2514383,3863769,2053739,2967116,2909594,3813438,1992024,4228816,3522280,3485581,4570293,2231259,5118636,2765810,2716488,4027389,4613502,5604049,3018485,5985562,3872472,2184932,3942357,4627870,6527847,3503282,3640012,2572539,3528661,1093245,3607289,5956669,3977544,2320834,9295431,5912336,4241191,6408975,3601934,4492269,5819004,4986168,6059455,6226998,6790729"),
  ("opt", "read-history  2005-12-15 15:49:53 (900 s) 495927,524616,129041,878800,3720852,5079672,3100079,2354836,5676649,897733,803489,1290198,722290,2668752,388945,1012224,555105,551926,229237,625384,540183,547260,90666,679625,1823270,533404,97951,508876,556610,2105237,598138,565197,932198,572469,183924,1559088,1780955,1142806,169486,636926,591644,546922,139874,506721,505666,534865,61575,501584,551601,520631,3605541,512796,522323,516478,50845,495963,1254899,512301,488825,1912180,755547,536891,581127,508460,535061,703609,47967,500767,536309,535017,102464,843770,569524,535657,76643,544786,540226,555237,63490,518246,549489,555350,67611,546639,560787,3329531,2367402,534145,551491,576446,60131,1561718,541703,557599,322727,4659545"),
  ("contact", "tor@science.brainzentrum.de"),
  ("reject", "*:*"),
)

RELAY_SERVER_FOOTER = (
  ("router-signature", "\n-----BEGIN SIGNATURE-----%s-----END SIGNATURE-----" % ACTUAL_SIGNATURE_BLOB),
)



def no_op():
  def _no_op(*args): pass
  return _no_op

def return_value(value):
  def _return_value(*args): return value
  return _return_value

def return_true(): return return_value(True)
def return_false(): return return_value(False)
def return_none(): return return_value(None)

def return_for_args(args_to_return_value, default = None):
  """
  Returns a value if the arguments to it match something in a given
  'argument => return value' mapping. Otherwise, a default function
  is called with the arguments.
  
  :param dict args_to_return_value: mapping of arguments to the value we should provide
  :param functor default: returns the value of this function if the args don't match something that we have, we raise a ValueError by default
  """
  
  def _return_value(*args):
    # strip off the 'self' for mock clases
    if args and 'MockClass' in str(type(args[0])):
      args = args[1:] if len(args) > 2 else args[1]
    
    if args in args_to_return_value:
      return args_to_return_value[args]
    elif default is None:
      arg_label = ", ".join([str(v) for v in args])
      raise ValueError("Unrecognized argument sent for return_for_args(). Got '%s' but we only recognize '%s'." % (arg_label, ", ".join(args_to_return_value.keys())))
    else:
      return default(args)
  
  return _return_value

def raise_exception(exception):
  def _raise(*args): raise exception
  return _raise

def support_with(obj):
  """
  Provides no-op support for the 'with' keyword, adding __enter__ and __exit__
  methods to the object. The __enter__ provides the object itself and __exit__
  does nothing.
  
  :param object obj: object to support the 'with' keyword
  
  :returns: input object
  """
  
  obj.__dict__["__enter__"] = return_value(obj)
  obj.__dict__["__exit__"] = no_op()
  return obj

def mock(target, mock_call, target_module=None):
  """
  Mocks the given function, saving the initial implementation so it can be
  reverted later.
  
  The target_module only needs to be set if the results of
  'inspect.getmodule(target)' doesn't match the module that we want to mock
  (for instance, the 'os' module provides the platform module that it wraps
  like 'postix', which won't work).
  
  :param function target: function to be mocked
  :param functor mock_call: mocking to replace the function with
  :param module target_module: module that this is mocking, this defaults to the inspected value
  """
  
  if hasattr(target, "__dict__") and "mock_id" in target.__dict__:
    # we're overriding an already mocked function
    mocking_id = target.__dict__["mock_id"]
    target_module, target_function, _ = MOCK_STATE[mocking_id]
  else:
    # this is a new mocking, save the original state
    mocking_id = MOCK_ID.next()
    target_module = target_module or inspect.getmodule(target)
    target_function = target.__name__
    MOCK_STATE[mocking_id] = (target_module, target_function, target)
  
  mock_wrapper = lambda *args: mock_call(*args)
  mock_wrapper.__dict__["mock_id"] = mocking_id
  
  # mocks the function with this wrapper
  if hasattr(target, "__dict__"):
    target_module.__dict__[target_function] = mock_wrapper
  else:
    setattr(target_module, target.__name__, mock_call)

def mock_method(target_class, method_name, mock_call):
  """
  Mocks the given class method in a similar fashion as what mock() does for
  functions.
  
  :param class target_class: class with the method we want to mock
  :param str method_name: name of the method to be mocked
  :param functor mock_call: mocking to replace the method with
  """
  
  # Ideally callers could call us with just the method, for instance like...
  #   mock_method(MyClass.foo, mocking.return_true())
  #
  # However, while classes reference the methods they have the methods
  # themselves don't reference the class. This is unfortunate because it means
  # that we need to know both the class and method we're replacing.
  
  target_method = target_class.__dict__[method_name]
  
  if "mock_id" in target_method.__dict__:
    # we're overriding an already mocked method
    mocking_id = target_method.mock_id
    _, target_method, _ = MOCK_STATE[mocking_id]
  else:
    # this is a new mocking, save the original state
    mocking_id = MOCK_ID.next()
    MOCK_STATE[mocking_id] = (target_class, method_name, target_method)
  
  mock_wrapper = lambda *args: mock_call(*args)
  mock_wrapper.__dict__["mock_id"] = mocking_id
  
  # mocks the function with this wrapper
  target_class.__dict__[method_name] = mock_wrapper

def revert_mocking():
  """
  Reverts any mocking done by this function.
  """
  
  # Reverting mocks in reverse order. If we properly reuse mock_ids then this
  # shouldn't matter, but might as well be safe.
  
  mock_ids = MOCK_STATE.keys()
  mock_ids.sort()
  mock_ids.reverse()
  
  for mock_id in mock_ids:
    module, function, impl = MOCK_STATE[mock_id]
    
    if module == __builtin__:
      setattr(__builtin__, function, impl)
    else:
      module.__dict__[function] = impl
    
    del MOCK_STATE[mock_id]
  
  MOCK_STATE.clear()

def get_real_function(function):
  """
  Provides the original, non-mocked implementation for a function or method.
  This simply returns the current implementation if it isn't being mocked.
  
  :param function function: function to look up the original implementation of
  
  :returns: original implementation of the function
  """
  
  if "mock_id" in function.__dict__:
    mocking_id = function.__dict__["mock_id"]
    return MOCK_STATE[mocking_id][2]
  else:
    return function

def get_all_combinations(attr, include_empty = False):
  """
  Provides an iterator for all combinations of a set of attributes. For
  instance...
  
  ::
  
    >>> list(test.mocking.get_all_combinations(["a", "b", "c"]))
    [('a',), ('b',), ('c',), ('a', 'b'), ('a', 'c'), ('b', 'c'), ('a', 'b', 'c')]
  
  :param list attr: attributes to provide combinations for
  :param bool include_empty: includes an entry with zero items if True
  :returns: iterator for all combinations
  """
  
  # Makes an itertools.product() call for 'i' copies of attr...
  #
  # * itertools.product(attr) => all one-element combinations
  # * itertools.product(attr, attr) => all two-element combinations
  # * ... etc
  
  if include_empty: yield ()
  
  seen = set()
  for i in xrange(1, len(attr) + 1):
    product_arg = [attr for _ in xrange(i)]
    
    for item in itertools.product(*product_arg):
      # deduplicate, sort, and only provide if we haven't seen it yet
      item = tuple(sorted(set(item)))
      
      if not item in seen:
        seen.add(item)
        yield item

def get_object(object_class, methods = None):
  """
  Provides a mock Controller instance. Its methods are mocked with the given
  replacements, and calling any others will result in an exception.
  
  :param class object_class: class that we're making an instance of
  :param dict methods: mapping of method names to their mocked implementation
  
  :returns: stem.control.Controller instance
  """
  
  if methods is None:
    methods = {}
  
  mock_methods = {}
  
  for method_name in dir(object_class):
    if method_name in methods:
      mock_methods[method_name] = methods[method_name]
    elif method_name.startswith('__') and method_name.endswith('__'):
      pass # messing with most private methods makes for a broken mock object
    else:
      mock_methods[method_name] = raise_exception(ValueError("Unexpected call of '%s' on a mock object" % method_name))
  
  # makes it so our constructor won't need any arguments
  mock_methods['__init__'] = no_op()
  
  mock_class = type('MockClass', (object_class,), mock_methods)
  
  return mock_class()

def get_message(content, reformat = True):
  """
  Provides a ControlMessage with content modified to be parsable. This makes
  the following changes unless 'reformat' is false...
  
  * ensures the content ends with a newline
  * newlines are replaced with a carriage return and newline pair
  
  :param str content: base content for the controller message
  :param str reformat: modifies content to be more accommodating to being parsed
  
  :returns: stem.socket.ControlMessage instance
  """
  
  if reformat:
    if not content.endswith("\n"): content += "\n"
    content = content.replace("\n", "\r\n")
  
  return stem.socket.recv_message(StringIO.StringIO(content))

def get_protocolinfo_response(**attributes):
  """
  Provides a ProtocolInfoResponse, customized with the given attributes. The
  base instance is minimal, with its version set to one and everything else
  left with the default.
  
  :param dict attributes: attributes to customize the response with
  
  :returns: stem.response.protocolinfo.ProtocolInfoResponse instance
  """
  
  protocolinfo_response = get_message("250-PROTOCOLINFO 1\n250 OK")
  stem.response.convert("PROTOCOLINFO", protocolinfo_response)
  
  for attr in attributes:
    protocolinfo_response.__dict__[attr] = attributes[attr]
  
  return protocolinfo_response

def _get_descriptor_content(attr = None, exclude = (), header_template = (), footer_template = ()):
  """
  Constructs a minimal descriptor with the given attributes. The content we
  provide back is of the form...
  
  * header_template (with matching attr filled in)
  * unused attr entries
  * footer_template (with matching attr filled in)
  
  So for instance...
  
  ::
  
    get_descriptor_content(
      attr = {'nickname': 'caerSidi', 'contact': 'atagar'},
      header_template = (
        ('nickname', 'foobar'),
        ('fingerprint', '12345'),
      ),
    )
  
  ... would result in...
  
  ::
  
    nickname caerSidi
    fingerprint 12345
    contact atagar
  
  :param dict attr: keyword/value mappings to be included in the descriptor
  :param list exclude: mandatory keywords to exclude from the descriptor
  :param tuple header_template: key/value pairs for mandatory fields before unrecognized content
  :param tuple footer_template: key/value pairs for mandatory fields after unrecognized content
  
  :returns: str with the requested descriptor content
  """
  
  header_content, footer_content = [], []
  if attr is None: attr = {}
  attr = dict(attr) # shallow copy since we're destructive
  
  for content, template in ((header_content, header_template),
                           (footer_content, footer_template)):
    for keyword, value in template:
      if keyword in exclude: continue
      elif keyword in attr:
        value = attr[keyword]
        del attr[keyword]
      
      if value is None: continue
      elif value == "":
        content.append(keyword)
      elif keyword == "onion-key" or keyword == "signing-key" or keyword == "router-signature":
        content.append("%s%s" % (keyword, value))
      else:
        content.append("%s %s" % (keyword, value))
  
  remainder = []
  
  for k, v in attr.items():
    if v: remainder.append("%s %s" % (k, v))
    else: remainder.append(k)
  
  return "\n".join(header_content + remainder + footer_content)

def get_relay_server_descriptor(attr = None, exclude = (), content = False):
  """
  Provides the descriptor content for...
  stem.descriptor.server_descriptor.RelayDescriptor
  
  :param dict attr: keyword/value mappings to be included in the descriptor
  :param list exclude: mandatory keywords to exclude from the descriptor
  :param bool content: provides the str content of the descriptor rather than the class if True
  
  :returns: RelayDescriptor for the requested descriptor content
  """
  
  desc_content = _get_descriptor_content(attr, exclude, RELAY_SERVER_HEADER, RELAY_SERVER_FOOTER)
  
  if content:
    return desc_content
  else:
    return stem.descriptor.server_descriptor.RelayDescriptor(desc_content, validate = True)

def get_bridge_server_descriptor(attr = None, exclude = (), content = False):
  """
  Provides the descriptor content for...
  stem.descriptor.server_descriptor.BridgeDescriptor
  
  :param dict attr: keyword/value mappings to be included in the descriptor
  :param list exclude: mandatory keywords to exclude from the descriptor
  :param bool content: provides the str content of the descriptor rather than the class if True
  
  :returns: BridgeDescriptor for the requested descriptor content
  """
  
  desc_content = _get_descriptor_content(attr, exclude, BRIDGE_SERVER_HEADER)
  
  if content:
    return desc_content
  else:
    return stem.descriptor.server_descriptor.BridgeDescriptor(desc_content, validate = True)

def get_relay_extrainfo_descriptor(attr = None, exclude = (), content = False):
  """
  Provides the descriptor content for...
  stem.descriptor.extrainfo_descriptor.RelayExtraInfoDescriptor
  
  :param dict attr: keyword/value mappings to be included in the descriptor
  :param list exclude: mandatory keywords to exclude from the descriptor
  :param bool content: provides the str content of the descriptor rather than the class if True
  
  :returns: RelayExtraInfoDescriptor for the requested descriptor content
  """
  
  desc_content = _get_descriptor_content(attr, exclude, RELAY_EXTRAINFO_HEADER, RELAY_EXTRAINFO_FOOTER)
  
  if content:
    return desc_content
  else:
    return stem.descriptor.extrainfo_descriptor.RelayExtraInfoDescriptor(desc_content, validate = True)

def get_bridge_extrainfo_descriptor(attr = None, exclude = (), content = False):
  """
  Provides the descriptor content for...
  stem.descriptor.extrainfo_descriptor.BridgeExtraInfoDescriptor
  
  :param dict attr: keyword/value mappings to be included in the descriptor
  :param list exclude: mandatory keywords to exclude from the descriptor
  :param bool content: provides the str content of the descriptor rather than the class if True
  
  :returns: BridgeExtraInfoDescriptor for the requested descriptor content
  """
  
  desc_content = _get_descriptor_content(attr, exclude, BRIDGE_EXTRAINFO_HEADER, BRIDGE_EXTRAINFO_FOOTER)
  
  if content:
    return desc_content
  else:
    return stem.descriptor.extrainfo_descriptor.BridgeExtraInfoDescriptor(desc_content, validate = True)

def get_router_status_entry_v2(attr = None, exclude = (), content = False):
  """
  Provides the descriptor content for...
  stem.descriptor.router_status_entry.RouterStatusEntryV2
  
  :param dict attr: keyword/value mappings to be included in the descriptor
  :param list exclude: mandatory keywords to exclude from the descriptor
  :param bool content: provides the str content of the descriptor rather than the class if True
  
  :returns: RouterStatusEntryV2 for the requested descriptor content
  """
  
  desc_content = _get_descriptor_content(attr, exclude, ROUTER_STATUS_ENTRY_V2_HEADER)
  
  if content:
    return desc_content
  else:
    return stem.descriptor.router_status_entry.RouterStatusEntryV2(desc_content, validate = True)

def get_router_status_entry_v3(attr = None, exclude = (), content = False):
  """
  Provides the descriptor content for...
  stem.descriptor.router_status_entry.RouterStatusEntryV3
  
  :param dict attr: keyword/value mappings to be included in the descriptor
  :param list exclude: mandatory keywords to exclude from the descriptor
  :param bool content: provides the str content of the descriptor rather than the class if True
  
  :returns: RouterStatusEntryV3 for the requested descriptor content
  """
  
  desc_content = _get_descriptor_content(attr, exclude, ROUTER_STATUS_ENTRY_V3_HEADER)
  
  if content:
    return desc_content
  else:
    return stem.descriptor.router_status_entry.RouterStatusEntryV3(desc_content, validate = True)

def get_router_status_entry_micro_v3(attr = None, exclude = (), content = False):
  """
  Provides the descriptor content for...
  stem.descriptor.router_status_entry.RouterStatusEntryMicroV3
  
  :param dict attr: keyword/value mappings to be included in the descriptor
  :param list exclude: mandatory keywords to exclude from the descriptor
  :param bool content: provides the str content of the descriptor rather than the class if True
  
  :returns: RouterStatusEntryMicroV3 for the requested descriptor content
  """
  
  desc_content = _get_descriptor_content(attr, exclude, ROUTER_STATUS_ENTRY_MICRO_V3_HEADER)
  
  if content:
    return desc_content
  else:
    return stem.descriptor.router_status_entry.RouterStatusEntryMicroV3(desc_content, validate = True)

def get_directory_authority(attr = None, exclude = (), is_vote = False, content = False):
  """
  Provides the descriptor content for...
  stem.descriptor.networkstatus.DirectoryAuthority
  
  :param dict attr: keyword/value mappings to be included in the descriptor
  :param list exclude: mandatory keywords to exclude from the descriptor
  :param bool is_vote: True if this is for a vote, False if it's for a consensus
  :param bool content: provides the str content of the descriptor rather than the class if True
  
  :returns: DirectoryAuthority for the requested descriptor content
  """
  
  if attr is None:
    attr = {}
  
  if not is_vote:
    # entries from a consensus also have a mandatory 'vote-digest' field
    if not ('vote-digest' in attr or (exclude and 'vote-digest' in exclude)):
      attr['vote-digest'] = '0B6D1E9A300B895AA2D0B427F92917B6995C3C1C'
  
  desc_content = _get_descriptor_content(attr, exclude, AUTHORITY_HEADER)
  
  if is_vote:
    desc_content += "\n" + str(get_key_certificate())
  
  if content:
    return desc_content
  else:
    return stem.descriptor.networkstatus.DirectoryAuthority(desc_content, validate = True, is_vote = is_vote)

def get_key_certificate(attr = None, exclude = (), content = False):
  """
  Provides the descriptor content for...
  stem.descriptor.networkstatus.KeyCertificate
  
  :param dict attr: keyword/value mappings to be included in the descriptor
  :param list exclude: mandatory keywords to exclude from the descriptor
  :param bool content: provides the str content of the descriptor rather than the class if True
  
  :returns: KeyCertificate for the requested descriptor content
  """
  
  desc_content = _get_descriptor_content(attr, exclude, KEY_CERTIFICATE_HEADER, KEY_CERTIFICATE_FOOTER)
  
  if content:
    return desc_content
  else:
    return stem.descriptor.networkstatus.KeyCertificate(desc_content, validate = True)

def get_network_status_document_v2(attr = None, exclude = (), routers = None, content = False):
  """
  Provides the descriptor content for...
  stem.descriptor.networkstatus.NetworkStatusDocumentV2
  
  :param dict attr: keyword/value mappings to be included in the descriptor
  :param list exclude: mandatory keywords to exclude from the descriptor
  :param list routers: router status entries to include in the document
  :param bool content: provides the str content of the descriptor rather than the class if True
  
  :returns: NetworkStatusDocumentV2 for the requested descriptor content
  """
  
  desc_content = _get_descriptor_content(attr, exclude, NETWORK_STATUS_DOCUMENT_HEADER_V2, NETWORK_STATUS_DOCUMENT_FOOTER_V2)
  
  if content:
    return desc_content
  else:
    return stem.descriptor.networkstatus.NetworkStatusDocumentV2(desc_content, validate = True)

def get_network_status_document_v3(attr = None, exclude = (), authorities = None, routers = None, content = False):
  """
  Provides the descriptor content for...
  stem.descriptor.networkstatus.NetworkStatusDocumentV3
  
  :param dict attr: keyword/value mappings to be included in the descriptor
  :param list exclude: mandatory keywords to exclude from the descriptor
  :param list authorities: directory authorities to include in the document
  :param list routers: router status entries to include in the document
  :param bool content: provides the str content of the descriptor rather than the class if True
  
  :returns: NetworkStatusDocumentV3 for the requested descriptor content
  """
  
  if attr is None:
    attr = {}
  
  # add defaults only found in a vote, consensus, or microdescriptor
  
  if attr.get("vote-status") == "vote":
    extra_defaults = {
      "consensus-methods": "1 9",
      "published": "2012-09-02 22:00:00",
    }
  else:
    extra_defaults = {
      "consensus-method": "9",
    }
  
  if "microdesc" in attr.get("network-status-version", ""):
    extra_defaults.update({
      "directory-signature": "sha256 " + NETWORK_STATUS_DOCUMENT_FOOTER[2][1],
    })
  
  for k, v in extra_defaults.items():
    if not (k in attr or (exclude and k in exclude)):
      attr[k] = v
  
  desc_content = _get_descriptor_content(attr, exclude, NETWORK_STATUS_DOCUMENT_HEADER, NETWORK_STATUS_DOCUMENT_FOOTER)
  
  # inject the authorities and/or routers between the header and footer
  if authorities:
    footer_div = desc_content.find("\ndirectory-footer") + 1
    authority_content = "\n".join([str(a) for a in authorities]) + "\n"
    desc_content = desc_content[:footer_div] + authority_content + desc_content[footer_div:]
  
  if routers:
    footer_div = desc_content.find("\ndirectory-footer") + 1
    router_content = "\n".join([str(r) for r in routers]) + "\n"
    desc_content = desc_content[:footer_div] + router_content + desc_content[footer_div:]
  
  if content:
    return desc_content
  else:
    return stem.descriptor.networkstatus.NetworkStatusDocumentV3(desc_content, validate = True)

