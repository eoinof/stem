"""
Handlers for text configuration files. Configurations are simple string to
string mappings, with the configuration files using the following rules...

* the key/value is separated by a space
* anything after a "#" is ignored as a comment
* excess whitespace is trimmed
* empty lines are ignored
* multi-line values can be defined by following the key with lines starting
  with a '|'

For instance...

::

  # This is my sample config
  user.name Galen
  user.password yabba1234 # here's an inline comment
  user.notes takes a fancy to pepperjack cheese
  blankEntry.example
  
  msg.greeting
  |Multi-line message exclaiming of the
  |wonder and awe that is pepperjack!

... would be loaded as...

::

  config = {
    "user.name": "Galen",
    "user.password": "yabba1234",
    "user.notes": "takes a fancy to pepperjack cheese",
    "blankEntry.example": "",
    "msg.greeting": "Multi-line message exclaiming of the\\nwonder and awe that is pepperjack!",
  }

Configurations are loaded or saved via the :class:`~stem.util.conf.Config`
class. The :class:`~stem.util.conf.Config` can be be used directly with its
:func:`~stem.util.conf.Config.get` and :func:`~stem.util.conf.Config.set`
methods, but usually modules will want a local dictionary with just the
configurations that it cares about. This can be done a couple ways...

* **Independent Dictionary**

To simply get a dictionary that has configurations use the
:func:`~stem.util.conf.Config.synchronize` method. This takes as an argument
a dictionary with the default values.

For instance, lets say that you had a file at '/home/atagar/user_config'
with...

::

  username waddle_doo
  permissions.ssh true
  some.extra.stuff foobar

... then run...

::

  >>> from stem.util.conf import get_config
  >>> my_module_config = {
  ...   "username": "default",
  ...   "permissions.ssh": False,
  ...   "permissions.sudo": False,
  ... }
  
  >>> config = get_config("user_config")
  >>> config.load("/home/atagar/user_config")
  >>> config.synchronize(my_module_config)
  
  >>> print my_module_config
  {'username': 'waddle_doo', 'permissions.sudo': False, 'permissions.ssh': True}

The configuration file just contains string mappings, but the
:class:`~stem.util.conf.Config` attempts to convert those values to be the same
types as the dictionary's defaults. For more information on how type inferences
work see the :func:`~stem.util.conf.Config.get` method.

* **Linked Dictionary**

Alternatively you can get a read-only dictionary that stays in sync with the
:class:`~stem.util.conf.Config` by using the
:func:`~stem.util.conf.config_dict` function...

::

  >>> # Make a dictionary that watches the 'user_config' configuration for changes.
  
  >>> from stem.util.conf import config_dict
  >>> my_module_config = config_dict("user_config", {
  ...   "username": "default",
  ...   "permissions.ssh": False,
  ...   "permissions.sudo": False,
  ... })
  >>> print my_module_config
  {'username': 'default', 'permissions.sudo': False, 'permissions.ssh': False}
  
  >>> # Something (maybe another module) loads the config, causing the
  >>> # my_module_config above to be updated.
  
  >>> from stem.util.conf import get_config
  >>> config = get_config("user_config")
  >>> config.load("/home/atagar/user_config")
  
  >>> print my_module_config
  {'username': 'waddle_doo', 'permissions.sudo': False, 'permissions.ssh': True}
  
  >>> config.set('username', 'ness')
  >>> print my_module_config
  {'username': 'ness', 'permissions.sudo': False, 'permissions.ssh': True}

**Module Overview:**

::

  config_dict - provides a dictionary that's kept synchronized with a config
  get_config - singleton for getting configurations
  
  Config - Custom configuration
    |- load - reads a configuration file
    |- save - writes the current configuration to a file
    |- clear - empties our loaded configuration contents
    |- synchronize - replaces mappings in a dictionary with the config's values
    |- add_listener - notifies the given listener when an update occurs
    |- clear_listeners - removes any attached listeners
    |- keys - provides keys in the loaded configuration
    |- set - sets the given key/value pair
    |- unused_keys - provides keys that have never been requested
    |- get - provides the value for a given key, with type inference
    |- get_value - provides the value for a given key as a string
    |- get_str_csv - gets a value as a comma separated list of strings
    +- get_int_csv - gets a value as a comma separated list of integers
"""

from __future__ import with_statement

import threading

import stem.util.log as log

CONFS = {}  # mapping of identifier to singleton instances of configs

class _SyncListener(object):
  def __init__(self, config_dict, interceptor):
    self.config_dict = config_dict
    self.interceptor = interceptor
  
  def update(self, config, key):
    if key in self.config_dict:
      new_value = config.get(key, self.config_dict[key])
      if new_value == self.config_dict[key]: return # no change
      
      if self.interceptor:
        interceptor_value = self.interceptor(key, new_value)
        if interceptor_value: new_value = interceptor_value
      
      self.config_dict[key] = new_value

def config_dict(handle, conf_mappings, handler = None):
  """
  Makes a dictionary that stays synchronized with a configuration. The process
  for staying in sync is similar to the :class:`~stem.util.conf.Config` class'
  :func:`~stem.util.conf.Config.synchronize` method, only changing the
  dictionary's values if we're able to cast to the same type.
  
  If a handler is provided then this is called just prior to assigning new
  values to the config_dict. The handler function is expected to accept the
  (key, value) for the new values and return what we should actually insert
  into the dictionary. If this returns None then the value is updated as
  normal.
  
  :param str handle: unique identifier for a config instance
  :param dict conf_mappings: config key/value mappings used as our defaults
  :param functor handler: function referred to prior to assigning values
  """
  
  selected_config = get_config(handle)
  selected_config.add_listener(_SyncListener(conf_mappings, handler).update)
  return conf_mappings

def get_config(handle):
  """
  Singleton constructor for configuration file instances. If a configuration
  already exists for the handle then it's returned. Otherwise a fresh instance
  is constructed.
  
  :param str handle: unique identifier used to access this config instance
  """
  
  if not handle in CONFS: CONFS[handle] = Config()
  return CONFS[handle]

class Config(object):
  """
  Handler for easily working with custom configurations, providing persistence
  to and from files. All operations are thread safe.
  
  **Example usage:**
  
  User has a file at '/home/atagar/myConfig' with...
  
  ::
  
    destination.ip 1.2.3.4
    destination.port blarg
    
    startup.run export PATH=$PATH:~/bin
    startup.run alias l=ls
  
  And they have a script with...
  
  ::
  
    import stem.util.conf
    
    # Configuration values we'll use in this file. These are mappings of
    # configuration keys to the default values we'll use if the user doesn't
    # have something different in their config file (or it doesn't match this
    # type).
    
    ssh_config = {"login.user": "atagar",
                  "login.password": "pepperjack_is_awesome!",
                  "destination.ip": "127.0.0.1",
                  "destination.port": 22,
                  "startup.run": []}
    
    # Makes an empty config instance with the handle of 'ssh_login'. This is
    # a singleton so other classes can fetch this same configuration from
    # this handle.
    
    user_config = stem.util.conf.get_config("ssh_login")
    
    # Loads the user's configuration file, warning if this fails.
    
    try:
      user_config.load("/home/atagar/myConfig")
    except IOError, exc:
      print "Unable to load the user's config: %s" % exc
    
    # Replaces the contents of ssh_config with the values from the user's
    # config file if...
    #
    # * the key is present in the config file
    # * we're able to convert the configuration file's value to the same type
    #   as what's in the mapping (see the Config.get() method for how these
    #   type inferences work)
    #
    # For instance in this case...
    #
    # * the login values are left alone because they aren't in the user's
    #   config file
    #
    # * the 'destination.port' is also left with the value of 22 because we
    #   can't turn "blarg" into an integer
    #
    # The other values are replaced, so ssh_config now becomes...
    #
    # {"login.user": "atagar",
    #  "login.password": "pepperjack_is_awesome!",
    #  "destination.ip": "1.2.3.4",
    #  "destination.port": 22,
    #  "startup.run": ["export PATH=$PATH:~/bin", "alias l=ls"]}
    #
    # Information for what values fail to load and why are reported to
    # 'stem.util.log'.
    
    user_config.synchronize(ssh_config)
  """
  
  def __init__(self):
    self._path = None        # location we last loaded from or saved to
    self._contents = {}      # configuration key/value pairs
    self._raw_contents = []  # raw contents read from configuration file
    self._listeners = []     # functors to be notified of config changes
    
    # used for both _contents and _raw_contents access
    self._contents_lock = threading.RLock()
    
    # keys that have been requested (used to provide unused config contents)
    self._requested_keys = set()
  
  def load(self, path = None):
    """
    Reads in the contents of the given path, adding its configuration values
    to our current contents.
    
    :param str path: file path to be loaded, this uses the last loaded path if
      not provided
    
    :raises:
      * **IOError** if we fail to read the file (it doesn't exist, insufficient
        permissions, etc)
      * **ValueError** if no path was provided and we've never been provided one
    """
    
    if path:
      self._path = path
    elif not self._path:
      raise ValueError("Unable to load configuration: no path provided")
    
    with open(self._path, "r") as config_file:
      read_contents = config_file.readlines()
    
    with self._contents_lock:
      self._raw_contents = read_contents
      remainder = list(self._raw_contents)
      
      while remainder:
        line = remainder.pop(0)
        
        # strips any commenting or excess whitespace
        comment_start = line.find("#")
        if comment_start != -1: line = line[:comment_start]
        line = line.strip()
        
        # parse the key/value pair
        if line:
          try:
            key, value = line.split(" ", 1)
            value = value.strip()
          except ValueError:
            log.debug("Config entry '%s' is expected to be of the format 'Key Value', defaulting to '%s' -> ''" % (line, line))
            key, value = line, ""
          
          if not value:
            # this might be a multi-line entry, try processing it as such
            multiline_buffer = []
            
            while remainder and remainder[0].lstrip().startswith("|"):
              content = remainder.pop(0).lstrip()[1:] # removes '\s+|' prefix
              content = content.rstrip("\n")          # trailing newline
              multiline_buffer.append(content)
            
            if multiline_buffer:
              self.set(key, "\n".join(multiline_buffer), False)
              continue
          
          self.set(key, value, False)
  
  def save(self, path = None):
    """
    Saves configuration contents to disk. If a path is provided then it
    replaces the configuration location that we track.
    
    :param str path: location to be saved to
    
    :raises: **ValueError** if no path was provided and we've never been provided one
    """
    
    if path:
      self._path = path
    elif not self._path:
      raise ValueError("Unable to save configuration: no path provided")
    
    # TODO: when we drop python 2.5 compatibility we can simplify this
    with self._contents_lock:
      with open(self._path, 'w') as output_file:
        for entry_key in sorted(self.keys()):
          for entry_value in self.get_value(entry_key, multiple = True):
            # check for multi line entries
            if "\n" in entry_value: entry_value = "\n|" + entry_value.replace("\n", "\n|")
            
            output_file.write('%s %s\n' % (entry_key, entry_value))
  
  def clear(self):
    """
    Drops the configuration contents and reverts back to a blank, unloaded
    state.
    """
    
    with self._contents_lock:
      self._contents.clear()
      self._raw_contents = []
      self._requested_keys = set()
  
  def synchronize(self, conf_mappings, limits = None):
    """
    This takes a dictionary of 'config_key => default_value' mappings and
    changes the values to reflect our current configuration. This will leave
    the previous values alone if...
    
    * we don't have a value for that config_key
    * we can't convert our value to be the same type as the default_value
    
    For more information about how we convert types see our
    :func:`~stem.util.conf.Config.get` method.
    
    :param dict conf_mappings: configuration key/value mappings to be revised
    :param dict limits: mappings of limits on numeric values, expected to be of
      the form "configKey -> min" or "configKey -> (min, max)"
    """
    
    if limits is None: limits = {}
    
    for entry in conf_mappings.keys():
      val = self.get(entry, conf_mappings[entry])
      
      # if this was a numeric value then apply constraints
      if entry in limits and (isinstance(val, int) or isinstance(val, float)):
        if isinstance(limits[entry], tuple):
          val = max(val, limits[entry][0])
          val = min(val, limits[entry][1])
        else: val = max(val, limits[entry])
      
      # only use this value if it wouldn't change the type of the mapping (this
      # will only fail if the type isn't either a string or one of the types
      # recognized by the get method)
      
      if type(val) == type(conf_mappings[entry]):
        conf_mappings[entry] = val
  
  def add_listener(self, listener, backfill = True):
    """
    Registers the function to be notified of configuration updates. Listeners
    are expected to be functors which accept (config, key).
    
    :param functor listener: function to be notified when our configuration is changed
    :param bool backfill: calls the function with our current values if **True**
    """
    
    with self._contents_lock:
      self._listeners.append(listener)
      
      if backfill:
        for key in self.keys():
          listener(self, key)
  
  def clear_listeners(self):
    """
    Removes all attached listeners.
    """
    
    self._listeners = []
  
  def keys(self):
    """
    Provides all keys in the currently loaded configuration.
    
    :returns: **list** if strings for the configuration keys we've loaded
    """
    
    return self._contents.keys()
  
  def unused_keys(self):
    """
    Provides the configuration keys that have never been provided to a caller
    via the :func:`~stem.util.conf.Config.get`,
    :func:`~stem.util.conf.Config.get_value`, or
    :func:`~stem.util.conf.Config.synchronize` methods.
    
    :returns: **set** of configuration keys we've loaded but have never been requested
    """
    
    return set(self.keys()).difference(self._requested_keys)
  
  def set(self, key, value, overwrite = True):
    """
    Appends the given key/value configuration mapping, behaving the same as if
    we'd loaded this from a configuration file.
    
    :param str key: key for the configuration mapping
    :param str,list value: value we're setting the mapping to
    :param bool overwrite: replaces the previous value if **True**, otherwise
      the values are appended
    """
    
    with self._contents_lock:
      if isinstance(value, str):
        if not overwrite and key in self._contents: self._contents[key].append(value)
        else: self._contents[key] = [value]
        
        for listener in self._listeners: listener(self, key)
      elif isinstance(value, list) or isinstance(value, tuple):
        if not overwrite and key in self._contents:
          self._contents[key] += value
        else: self._contents[key] = value
        
        for listener in self._listeners: listener(self, key)
      else:
        raise ValueError("Config.set() only accepts str, list, or tuple. Provided value was a '%s'" % type(value))
  
  def get(self, key, default = None):
    """
    Fetches the given configuration, using the key and default value to
    determine the type it should be. Recognized inferences are:
    
    * **default is a boolean => boolean**
    
      * values are case insensitive
      * provides the default if the value isn't "true" or "false"
    
    * **default is an integer => int**
    
      * provides the default if the value can't be converted to an int
    
    * **default is a float => float**
    
      * provides the default if the value can't be converted to a float
    
    * **default is a list => list**
    
      * string contents for all configuration values with this key
    
    * **default is a tuple => tuple**
    
      * string contents for all configuration values with this key
    
    * **default is a dictionary => dict**
    
      * values without "=>" in them are ignored
      * values are split into key/value pairs on "=>" with extra whitespace
        stripped
    
    :param str key: config setting to be fetched
    :param default object: value provided if no such key exists or fails to be converted
    
    :returns: given configuration value with its type inferred with the above rules
    """
    
    is_multivalue = type(default) in (list, tuple, dict)
    val = self.get_value(key, default, is_multivalue)
    if val == default: return val # don't try to infer undefined values
    
    if isinstance(default, bool):
      if val.lower() == "true": val = True
      elif val.lower() == "false": val = False
      else:
        log.debug("Config entry '%s' is expected to be a boolean, defaulting to '%s'" % (key, str(default)))
        val = default
    elif isinstance(default, int):
      try: val = int(val)
      except ValueError:
        log.debug("Config entry '%s' is expected to be an integer, defaulting to '%i'" % (key, default))
        val = default
    elif isinstance(default, float):
      try: val = float(val)
      except ValueError:
        log.debug("Config entry '%s' is expected to be a float, defaulting to '%f'" % (key, default))
        val = default
    elif isinstance(default, list):
      pass # nothing special to do (already a list)
    elif isinstance(default, tuple):
      val = tuple(val)
    elif isinstance(default, dict):
      valMap = {}
      for entry in val:
        if "=>" in entry:
          entryKey, entryVal = entry.split("=>", 1)
          valMap[entryKey.strip()] = entryVal.strip()
        else:
          log.debug("Ignoring invalid %s config entry (expected a mapping, but \"%s\" was missing \"=>\")" % (key, entry))
      val = valMap
    
    return val
  
  def get_value(self, key, default = None, multiple = False):
    """
    This provides the current value associated with a given key.
    
    :param str key: config setting to be fetched
    :param object default: value provided if no such key exists
    :param bool multiple: provides back a list of all values if **True**,
      otherwise this returns the last loaded configuration value
    
    :returns: **str** or **list** of string configuration values associated
      with the given key, providing the default if no such key exists
    """
    
    with self._contents_lock:
      if key in self._contents:
        self._requested_keys.add(key)
        
        if multiple:
          return self._contents[key]
        else:
          return self._contents[key][-1]
      else:
        message_id = "stem.util.conf.missing_config_key_%s" % key
        log.log_once(message_id, log.TRACE, "config entry '%s' not found, defaulting to '%s'" % (key, default))
        return default
  
  def get_str_csv(self, key, default = None, count = None, sub_key = None):
    """
    Fetches the given key as a comma separated value.
    
    :param str key: config setting to be fetched, last if multiple exists
    :param object default: value provided if no such key exists or doesn't
      match the count
    :param int count: if set then the default is returned when the number of
      elements doesn't match this value
    :param str sub_key: handle the configuration entry as a dictionary and use
      this key within it
    
    :returns: **list** with the stripped values
    """
    
    if sub_key: conf_value = self.get(key, {}).get(sub_key)
    else: conf_value = self.get_value(key)
    
    if conf_value is None: return default
    elif not conf_value.strip(): return [] # empty string
    else:
      conf_comp = [entry.strip() for entry in conf_value.split(",")]
      
      # check if the count doesn't match
      if count != None and len(conf_comp) != count:
        msg = "Config entry '%s' is expected to be %i comma separated values" % (key, count)
        if default != None and (isinstance(default, list) or isinstance(default, tuple)):
          defaultStr = ", ".join([str(i) for i in default])
          msg += ", defaulting to '%s'" % defaultStr
        
        log.debug(msg)
        return default
      
      return conf_comp
  
  def get_int_csv(self, key, default = None, count = None, min_value = None, max_value = None, sub_key = None):
    """
    Fetches the given comma separated value, returning the default if the
    values aren't integers or don't follow the given constraints.
    
    :param str key: config setting to be fetched, last if multiple exists
    :param object default: value provided if no such key exists, doesn't match
      the count, values aren't all integers, or doesn't match the bounds
    :param int count: checks that the number of values matches this if set
    :param int min_value: checks that all values are over this if set
    :param int max_value: checks that all values are under this if set
    :param str sub_key: handle the configuration entry as a dictionary and use
      this key within it
    
    :returns: **list** with the stripped values
    """
    
    conf_comp = self.get_str_csv(key, default, count, sub_key)
    if conf_comp == default: return default
    
    # validates the input, setting the error_msg if there's a problem
    error_msg = None
    base_error_msg = "Config entry '%s' is expected to %%s" % key
    
    # includes our default value in the message
    if default != None and (isinstance(default, list) or isinstance(default, tuple)):
      default_str = ", ".join([str(i) for i in default])
      base_error_msg += ", defaulting to '%s'" % default_str
    
    for val in conf_comp:
      if not val.isdigit():
        error_msg = base_error_msg % "only have integer values"
        break
      else:
        if min_value != None and int(val) < min_value:
          error_msg = base_error_msg % "only have values over %i" % min_value
          break
        elif max_value != None and int(val) > max_value:
          error_msg = base_error_msg % "only have values less than %i" % max_value
          break
    
    if error_msg:
      log.debug(error_msg)
      return default
    else: return [int(val) for val in conf_comp]

