from __future__ import print_function
import cmd

from ZeekControl.exceptions import CommandSyntaxError, InvalidNodeError, LockError

class ExitValueCmd(cmd.Cmd):
    def cmdloop(self, intro=None):
        """Repeatedly issue a prompt, accept input, parse an initial prefix
        off the received input, and dispatch to action methods, passing them
        the remainder of the line as argument.

        """

        self.preloop()
        if self.use_rawinput and self.completekey:
            try:
                import readline
                self.old_completer = readline.get_completer()
                readline.set_completer(self.complete)
                readline.parse_and_bind(self.completekey + ": complete")
            except ImportError:
                pass
        try:
            if intro is not None:
                self.intro = intro
            if self.intro:
                self.stdout.write("%s\n" % self.intro)
            self._stopping = False
            success = True
            while not self._stopping:
                if self.cmdqueue:
                    line = self.cmdqueue.pop(0)
                else:
                    if self.use_rawinput:
                        try:
                            line = input(self.prompt)
                        except EOFError:
                            line = "EOF"
                    else:
                        self.stdout.write(self.prompt)
                        self.stdout.flush()
                        line = self.stdin.readline()
                        if not line:
                            line = "EOF"
                        else:
                            line = line.rstrip("\r\n")
                line = self.precmd(line)
                try:
                    success = self.onecmd(line)
                except (CommandSyntaxError, InvalidNodeError, LockError) as err:
                    # Note that here we do not attempt to catch all ZeekControl
                    # exceptions; letting some just terminate the program to
                    # avoid getting in an unknown state (e.g. error while
                    # reloading the config).
                    success = False
                    print("Error: %s" % err)
                self.postcmd(False, line)
            self.postloop()
        finally:
            if self.use_rawinput and self.completekey:
                try:
                    import readline
                    readline.set_completer(self.old_completer)
                except ImportError:
                    pass
        return success
