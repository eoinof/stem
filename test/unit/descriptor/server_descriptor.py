"""
Unit tests for stem.descriptor.server_descriptor.
"""

import datetime
import StringIO
import unittest

import stem.prereq
import stem.descriptor.server_descriptor
from stem.descriptor.server_descriptor import RelayDescriptor, BridgeDescriptor
import test.runner
from test.mocking import get_relay_server_descriptor, get_bridge_server_descriptor, CRYPTO_BLOB

class TestServerDescriptor(unittest.TestCase):
  def test_minimal_relay_descriptor(self):
    """
    Basic sanity check that we can parse a relay server descriptor with minimal
    attributes.
    """
    
    desc = get_relay_server_descriptor()
    
    self.assertEquals("caerSidi", desc.nickname)
    self.assertEquals("71.35.133.197", desc.address)
    self.assertEquals(None, desc.fingerprint)
    self.assertTrue(CRYPTO_BLOB in desc.onion_key)
    self.assertTrue(CRYPTO_BLOB in desc.signing_key)
    self.assertTrue(CRYPTO_BLOB in desc.signature)
  
  def test_with_opt(self):
    """
    Includes an 'opt <keyword> <value>' entry.
    """
    
    desc = get_relay_server_descriptor({"opt": "contact www.atagar.com/contact/"})
    self.assertEquals("www.atagar.com/contact/", desc.contact)
  
  def test_unrecognized_line(self):
    """
    Includes unrecognized content in the descriptor.
    """
    
    desc = get_relay_server_descriptor({"pepperjack": "is oh so tasty!"})
    self.assertEquals(["pepperjack is oh so tasty!"], desc.get_unrecognized_lines())
  
  def test_proceeding_line(self):
    """
    Includes a line prior to the 'router' entry.
    """
    
    desc_text = "hibernate 1\n" + get_relay_server_descriptor(content = True)
    self._expect_invalid_attr(desc_text)
  
  def test_trailing_line(self):
    """
    Includes a line after the 'router-signature' entry.
    """
    
    desc_text = get_relay_server_descriptor(content = True) + "\nhibernate 1"
    self._expect_invalid_attr(desc_text)
  
  def test_nickname_missing(self):
    """
    Constructs with a malformed router entry.
    """
    
    desc_text = get_relay_server_descriptor({"router": " 71.35.133.197 9001 0 0"}, content = True)
    self._expect_invalid_attr(desc_text, "nickname")
  
  def test_nickname_too_long(self):
    """
    Constructs with a nickname that is an invalid length.
    """
    
    desc_text = get_relay_server_descriptor({"router": "saberrider2008ReallyLongNickname 71.35.133.197 9001 0 0"}, content = True)
    self._expect_invalid_attr(desc_text, "nickname", "saberrider2008ReallyLongNickname")
  
  def test_nickname_invalid_char(self):
    """
    Constructs with an invalid relay nickname.
    """
    
    desc_text = get_relay_server_descriptor({"router": "$aberrider2008 71.35.133.197 9001 0 0"}, content = True)
    self._expect_invalid_attr(desc_text, "nickname", "$aberrider2008")
  
  def test_address_malformed(self):
    """
    Constructs with an invalid ip address.
    """
    
    desc_text = get_relay_server_descriptor({"router": "caerSidi 371.35.133.197 9001 0 0"}, content = True)
    self._expect_invalid_attr(desc_text, "address", "371.35.133.197")
  
  def test_port_too_high(self):
    """
    Constructs with an ORPort that is too large.
    """
    
    desc_text = get_relay_server_descriptor({"router": "caerSidi 71.35.133.197 900001 0 0"}, content = True)
    self._expect_invalid_attr(desc_text, "or_port", 900001)
  
  def test_port_malformed(self):
    """
    Constructs with an ORPort that isn't numeric.
    """
    
    desc_text = get_relay_server_descriptor({"router": "caerSidi 71.35.133.197 900a1 0 0"}, content = True)
    self._expect_invalid_attr(desc_text, "or_port")
  
  def test_port_newline(self):
    """
    Constructs with a newline replacing the ORPort.
    """
    
    desc_text = get_relay_server_descriptor({"router": "caerSidi 71.35.133.197 \n 0 0"}, content = True)
    self._expect_invalid_attr(desc_text, "or_port")
  
  def test_platform_empty(self):
    """
    Constructs with an empty platform entry.
    """
    
    desc_text = get_relay_server_descriptor({"platform": ""}, content = True)
    desc = RelayDescriptor(desc_text, validate = False)
    self.assertEquals("", desc.platform)
    
    # does the same but with 'platform ' replaced with 'platform'
    desc_text = desc_text.replace("platform ", "platform")
    desc = RelayDescriptor(desc_text, validate = False)
    self.assertEquals("", desc.platform)
  
  def test_protocols_no_circuit_versions(self):
    """
    Constructs with a protocols line without circuit versions.
    """
    
    desc_text = get_relay_server_descriptor({"opt": "protocols Link 1 2"}, content = True)
    self._expect_invalid_attr(desc_text, "circuit_protocols")
  
  def test_published_leap_year(self):
    """
    Constructs with a published entry for a leap year, and when the date is
    invalid.
    """
    
    desc_text = get_relay_server_descriptor({"published": "2011-02-29 04:03:19"}, content = True)
    self._expect_invalid_attr(desc_text, "published")
    
    desc_text = get_relay_server_descriptor({"published": "2012-02-29 04:03:19"}, content = True)
    expected_published = datetime.datetime(2012, 2, 29, 4, 3, 19)
    self.assertEquals(expected_published, RelayDescriptor(desc_text).published)
  
  def test_published_no_time(self):
    """
    Constructs with a published entry without a time component.
    """
    
    desc_text = get_relay_server_descriptor({"published": "2012-01-01"}, content = True)
    self._expect_invalid_attr(desc_text, "published")
  
  def test_read_and_write_history(self):
    """
    Parses a read-history and write-history entry. This is now a deprecated
    field for relay server descriptors but is still found in archives and
    extra-info descriptors.
    """
    
    for field in ("read-history", "write-history"):
      value = "2005-12-16 18:00:48 (900 s) 81,8848,8927,8927,83,8848"
      desc = get_relay_server_descriptor({"opt %s" % field: value})
      
      if field == "read-history":
        attr = (desc.read_history_end, desc.read_history_interval, desc.read_history_values)
      else:
        attr = (desc.write_history_end, desc.write_history_interval, desc.write_history_values)
      
      expected_end = datetime.datetime(2005, 12, 16, 18, 0, 48)
      expected_values = [81, 8848, 8927, 8927, 83, 8848]
      
      self.assertEquals(expected_end, attr[0])
      self.assertEquals(900, attr[1])
      self.assertEquals(expected_values, attr[2])
  
  def test_read_history_empty(self):
    """
    Parses a read-history with an empty value.
    """
    
    value = "2005-12-17 01:23:11 (900 s) "
    desc = get_relay_server_descriptor({"opt read-history": value})
    self.assertEquals(datetime.datetime(2005, 12, 17, 1, 23, 11), desc.read_history_end)
    self.assertEquals(900, desc.read_history_interval)
    self.assertEquals([], desc.read_history_values)
  
  def test_annotations(self):
    """
    Checks that content before a descriptor are parsed as annotations.
    """
    
    desc_text = "@pepperjack very tasty\n@mushrooms not so much\n"
    desc_text += get_relay_server_descriptor(content = True)
    desc_text += "\ntrailing text that should be ignored, ho hum"
    
    # running parse_file should provide an iterator with a single descriptor
    desc_iter = stem.descriptor.server_descriptor.parse_file(StringIO.StringIO(desc_text))
    desc_entries = list(desc_iter)
    self.assertEquals(1, len(desc_entries))
    desc = desc_entries[0]
    
    self.assertEquals("caerSidi", desc.nickname)
    self.assertEquals("@pepperjack very tasty", desc.get_annotation_lines()[0])
    self.assertEquals("@mushrooms not so much", desc.get_annotation_lines()[1])
    self.assertEquals({"@pepperjack": "very tasty", "@mushrooms": "not so much"}, desc.get_annotations())
    self.assertEquals([], desc.get_unrecognized_lines())
  
  def test_duplicate_field(self):
    """
    Constructs with a field appearing twice.
    """
    
    desc_text = get_relay_server_descriptor({"<replace>": ""}, content = True)
    desc_text = desc_text.replace("<replace>", "contact foo\ncontact bar")
    self._expect_invalid_attr(desc_text, "contact", "foo")
  
  def test_missing_required_attr(self):
    """
    Test making a descriptor with a missing required attribute.
    """
    
    for attr in stem.descriptor.server_descriptor.REQUIRED_FIELDS:
      desc_text = get_relay_server_descriptor(exclude = [attr], content = True)
      self.assertRaises(ValueError, RelayDescriptor, desc_text)
      
      # check that we can still construct it without validation
      desc = RelayDescriptor(desc_text, validate = False)
      
      # for one of them checks that the corresponding values are None
      if attr == "router":
        self.assertEquals(None, desc.nickname)
        self.assertEquals(None, desc.address)
        self.assertEquals(None, desc.or_port)
        self.assertEquals(None, desc.socks_port)
        self.assertEquals(None, desc.dir_port)
  
  def test_fingerprint_valid(self):
    """
    Checks that a fingerprint matching the hash of our signing key will validate.
    """
    
    if not stem.prereq.is_rsa_available():
      test.runner.skip(self, "(rsa module unavailable)")
      return
    
    fingerprint = "4F0C 867D F0EF 6816 0568 C826 838F 482C EA7C FE44"
    desc = get_relay_server_descriptor({"opt fingerprint": fingerprint})
    self.assertEquals(fingerprint.replace(" ", ""), desc.fingerprint)
  
  def test_fingerprint_invalid(self):
    """
    Checks that, with a correctly formed fingerprint, we'll fail validation if
    it doesn't match the hash of our signing key.
    """
    
    if not stem.prereq.is_rsa_available():
      test.runner.skip(self, "(rsa module unavailable)")
      return
    
    fingerprint = "4F0C 867D F0EF 6816 0568 C826 838F 482C EA7C FE45"
    desc_text = get_relay_server_descriptor({"opt fingerprint": fingerprint}, content = True)
    self._expect_invalid_attr(desc_text, "fingerprint", fingerprint.replace(" ", ""))
  
  def test_minimal_bridge_descriptor(self):
    """
    Basic sanity check that we can parse a descriptor with minimal attributes.
    """
    
    desc = get_bridge_server_descriptor()
    
    self.assertEquals("Unnamed", desc.nickname)
    self.assertEquals("10.45.227.253", desc.address)
    self.assertEquals(None, desc.fingerprint)
    self.assertEquals("006FD96BA35E7785A6A3B8B75FE2E2435A13BDB4", desc.digest())
    
    # check that we don't have crypto fields
    self.assertRaises(AttributeError, getattr, desc, "onion_key")
    self.assertRaises(AttributeError, getattr, desc, "signing_key")
    self.assertRaises(AttributeError, getattr, desc, "signature")
  
  def test_bridge_unsanitized(self):
    """
    Targeted check that individual unsanitized attributes will be detected.
    """
    
    unsanitized_attr = [
      {"router": "Unnamed 75.45.227.253 9001 0 0"},
      {"contact": "Damian"},
      {"or-address": "71.35.133.197:9001"},
      {"or-address": "[12ab:2e19:3bcf::02:9970]:9001"},
      {"onion-key": "\n-----BEGIN RSA PUBLIC KEY-----%s-----END RSA PUBLIC KEY-----" % CRYPTO_BLOB},
      {"signing-key": "\n-----BEGIN RSA PUBLIC KEY-----%s-----END RSA PUBLIC KEY-----" % CRYPTO_BLOB},
      {"router-signature": "\n-----BEGIN SIGNATURE-----%s-----END SIGNATURE-----" % CRYPTO_BLOB},
    ]
    
    for attr in unsanitized_attr:
      desc = get_bridge_server_descriptor(attr)
      self.assertFalse(desc.is_scrubbed())
  
  def test_bridge_unsanitized_relay(self):
    """
    Checks that parsing a normal relay descriptor as a bridge will fail due to
    its unsanatized content.
    """
    
    desc_text = get_relay_server_descriptor({"router-digest": "006FD96BA35E7785A6A3B8B75FE2E2435A13BDB4"}, content = True)
    desc = BridgeDescriptor(desc_text)
    self.assertFalse(desc.is_scrubbed())
  
  def test_router_digest(self):
    """
    Constructs with a router-digest line with both valid and invalid contents.
    """
    
    # checks with valid content
    
    router_digest = "068A2E28D4C934D9490303B7A645BA068DCA0504"
    desc = get_bridge_server_descriptor({"router-digest": router_digest})
    self.assertEquals(router_digest, desc.digest())
    
    # checks when missing
    
    desc_text = get_bridge_server_descriptor(exclude = ["router-digest"], content = True)
    self.assertRaises(ValueError, BridgeDescriptor, desc_text)
    
    # check that we can still construct it without validation
    desc = BridgeDescriptor(desc_text, validate = False)
    self.assertEquals(None, desc.digest())
    
    # checks with invalid content
    
    test_values = (
      "",
      "006FD96BA35E7785A6A3B8B75FE2E2435A13BDB44",
      "006FD96BA35E7785A6A3B8B75FE2E2435A13BDB",
      "006FD96BA35E7785A6A3B8B75FE2E2435A13BDBH",
    )
    
    for value in test_values:
      desc_text = get_bridge_server_descriptor({"router-digest": value}, content = True)
      self.assertRaises(ValueError, BridgeDescriptor, desc_text)
      
      desc = BridgeDescriptor(desc_text, validate = False)
      self.assertEquals(value, desc.digest())
  
  def test_or_address_v4(self):
    """
    Constructs a bridge descriptor with a sanatized IPv4 or-address entry.
    """
    
    desc = get_bridge_server_descriptor({"or-address": "10.45.227.253:9001"})
    self.assertEquals([("10.45.227.253", 9001, False)], desc.address_alt)
  
  def test_or_address_v6(self):
    """
    Constructs a bridge descriptor with a sanatized IPv6 or-address entry.
    """
    
    desc = get_bridge_server_descriptor({"or-address": "[fd9f:2e19:3bcf::02:9970]:9001"})
    self.assertEquals([("fd9f:2e19:3bcf::02:9970", 9001, True)], desc.address_alt)
  
  def test_or_address_multiple(self):
    """
    Constructs a bridge descriptor with multiple or-address entries and multiple ports.
    """
    
    desc_text = "\n".join((get_bridge_server_descriptor(content = True),
                          "or-address 10.45.227.253:9001,9005,80",
                          "or-address [fd9f:2e19:3bcf::02:9970]:443"))
    
    expected_address_alt = [
      ("10.45.227.253", 9001, False),
      ("10.45.227.253", 9005, False),
      ("10.45.227.253", 80, False),
      ("fd9f:2e19:3bcf::02:9970", 443, True),
    ]
    
    desc = BridgeDescriptor(desc_text)
    self.assertEquals(expected_address_alt, desc.address_alt)
  
  def _expect_invalid_attr(self, desc_text, attr = None, expected_value = None):
    """
    Asserts that construction will fail due to desc_text having a malformed
    attribute. If an attr is provided then we check that it matches an expected
    value when we're constructed without validation.
    """
    
    self.assertRaises(ValueError, RelayDescriptor, desc_text)
    desc = RelayDescriptor(desc_text, validate = False)
    
    if attr:
      # check that the invalid attribute matches the expected value when
      # constructed without validation
      
      self.assertEquals(expected_value, getattr(desc, attr))
    else:
      # check a default attribute
      self.assertEquals("caerSidi", desc.nickname)

