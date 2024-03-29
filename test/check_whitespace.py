"""
Performs a check that our python source code follows its whitespace conventions
which are...

* two space indentations
* tabs are the root of all evil and should be shot on sight
* standard newlines (\\n), not windows (\\r\\n) nor classic mac (\\r)
* no trailing whitespace unless the line is empty, in which case it should have
  the same indentation as the surrounding code

This also checks for 2.5 compatibility issues (yea, they're not whitespace but
it's so much easier to do here...):

* checks that anything using the 'with' keyword has...
  from __future__ import with_statement
"""

from __future__ import with_statement

import re
import os

# if ran directly then run over everything one level up
DEFAULT_TARGET = os.path.sep.join(__file__.split(os.path.sep)[:-1])

def get_issues(base_path = DEFAULT_TARGET):
  """
  Checks python source code in the given directory for whitespace issues.
  
  :param str base_path: directory to be iterated over
  
  :returns: dict of the form ``path => [(line_number, message)...]``
  """
  
  # TODO: This does not check that block indentations are two spaces because
  # differentiating source from string blocks ("""foo""") is more of a pita
  # than I want to deal with right now.
  
  issues = {}
  
  for file_path in _get_files_with_suffix(base_path):
    with open(file_path) as f: file_contents = f.read()
    lines, file_issues, prev_indent = file_contents.split("\n"), [], 0
    has_with_import, given_with_warning = False, False
    is_block_comment = False
    
    for i in xrange(len(lines)):
      whitespace, content = re.match("^(\s*)(.*)$", lines[i]).groups()
      
      if '"""' in content:
        is_block_comment = not is_block_comment
      
      if content == "from __future__ import with_statement":
        has_with_import = True
      elif content.startswith("with ") and content.endswith(":") \
        and not has_with_import and not given_with_warning and not is_block_comment:
        file_issues.append((i + 1, "missing 'with' import (from __future__ import with_statement)"))
        given_with_warning = True
      
      if "\t" in whitespace:
        file_issues.append((i + 1, "indentation has a tab"))
      elif "\r" in content:
        file_issues.append((i + 1, "contains a windows newline"))
      elif content != content.rstrip():
        file_issues.append((i + 1, "line has trailing whitespace"))
      elif content == '':
        # empty line, check its indentation against the previous and next line
        # with content
        
        next_indent = 0
        
        for k in xrange(i + 1, len(lines)):
          future_whitespace, future_content = re.match("^(\s*)(.*)$", lines[k]).groups()
          
          if future_content:
            next_indent = len(future_whitespace)
            break
        
        if not len(whitespace) in (prev_indent, next_indent):
          msg = "indentation should match surrounding content (%s spaces)"
          
          if prev_indent == next_indent:
            msg = msg % prev_indent
          elif prev_indent < next_indent:
            msg = msg % ("%i or %i" % (prev_indent, next_indent))
          else:
            msg = msg % ("%i or %i" % (next_indent, prev_indent))
          
          file_issues.append((i + 1, msg))
      else:
        # we had content and it's fine, making a note of its indentation
        prev_indent = len(whitespace)
    
    if file_issues:
      issues[file_path] = file_issues
  
  return issues

def _get_files_with_suffix(base_path, suffix = ".py"):
  """
  Iterates over files in a given directory, providing filenames with a certain
  suffix.
  
  :param str base_path: directory to be iterated over
  :param str suffix: filename suffix to look for
  
  :returns: iterator that yields the absolute path for files with the given suffix
  """
  
  if os.path.isfile(base_path):
    if base_path.endswith(suffix):
      yield base_path
  else:
    for root, _, files in os.walk(base_path):
      for filename in files:
        if filename.endswith(suffix):
          yield os.path.join(root, filename)

if __name__ == '__main__':
  issues = get_issues()
  
  for file_path in issues:
    print file_path
    
    for line_number, msg in issues[file_path]:
      line_count = "%-4s" % line_number
      print "  line %s %s" % (line_count, msg)
    
    print

