#
# Generates the dynamic parts of the ZeekControl documentation.
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


def print_indented(text, level):
    out = ""
    if not isinstance(text, list):
        text = text.splitlines()

    for line in text:
        out += "{} {}\n".format("    " * level, line)
    out += "\n"

    return out


# Prints API documentation for a class. Includes all methods tagged with
# @api(tag). (Use an unknown tag to not exclude all methods.) If header is
# False, the class's name and doc string is not included.
def print_class(cls, tag="", header=True):
    out = ""
    methods = {}

    for key, val in cls.__dict__.items():
        if not inspect.isfunction(val):
            continue

        if not "_doc" in val.__dict__:
            continue

        if val.__dict__["_doc"] == tag:
            methods[key] = val

    if header:
        out += f".. _{cls.__name__}:\n\n"
        out += f"Class ``{cls.__name__}``\n"
        out += "~~~~~~~~%s~~" % ("~" * len(cls.__name__))
        out += "\n\n"
        out += f"class **{cls.__name__}**\n"
        out += print_indented(inspect.getdoc(cls), 1)

    for name in sorted(methods.keys()):
        func = methods[name]

        args, varargs, keywords, defaults = inspect.getargspec(func)

        out += print_indented(f".. _{cls.__name__}.{name}:", 1)
        out += print_indented("**{}** ({})".format(name, ", ".join(args)), 1)
        out += print_indented(inspect.getdoc(func), 2)

    return out
