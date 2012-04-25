#
# Generates the dynamic parts of the BroControl documentation.
#

import inspect

def api(*deco_args):
    if len(deco_args) == 1 and callable(deco_args[0]):
        # No argument to decorator.
        method = deco_args[0]
        method._doc = ""
        return method

    else:
        # Tag argument.
        def _api(method):
            method._doc = deco_args[0]
            return method
        return _api

def printIndented(str, level):
    if not isinstance(str, list):
        str = str.split("\n")

    for line in str:
        print "    " * level, line
    print

# Prints API documentation for a class. Includes all methods tagged with
# @api(tag). (Use an unknown tag to not exclude all methods.) If header is
# False, the class's name and doc string is not included.
def printClass(cls, tag="", header=True):
    methods = {}

    for (key, val) in cls.__dict__.items():
        if not inspect.isfunction(val):
            continue

        if not "_doc" in val.__dict__:
            continue

        if val.__dict__["_doc"] == tag:
            methods[key] = val

    if header:
        print ".. _%s:" % cls.__name__
        print
        print "Class ``%s``" % cls.__name__
        print "~~~~~~~~%s~~" % "~" * len(cls.__name__)
        print
        print "class **%s**" % cls.__name__
        printIndented(inspect.getdoc(cls), 1)

    for name in sorted(methods.keys()):
        func = methods[name]

        (args, varargs, keywords, defaults) = inspect.getargspec(func)

        printIndented(".. _%s.%s:" % (cls.__name__, name), 1)
        printIndented("**%s** (%s)" % (name, ", ".join(args)), 1)
        printIndented(inspect.getdoc(func), 2)

if __name__ == "__main__":
    # Print documentation.
    import plugin
    import node

    printClass(plugin.Plugin, tag="no-methods")
    printClass(plugin.Plugin, header=False)
    printClass(plugin.Plugin, "override", header=False)

    printClass(node.Node)

