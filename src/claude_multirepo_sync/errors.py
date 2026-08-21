"""Exceptions shared by the sync commands."""


class SyncError(Exception):
    """An expected failure - a git conflict, a lost push race - not a bug.

    Its message is what lands in the marker file, so callers pass the failure
    detail as extra arguments rather than pre-formatting it.
    """

    def __init__(self, *args, marker):
        super().__init__(*args)
        self.marker = marker

    def __str__(self):
        # Git leaves one of stdout/stderr empty most of the time; skip the blanks.
        return "\n".join(str(arg) for arg in self.args if arg)

    def record(self):
        """Persist the failure where the next session will find it.

        A method rather than something the constructor does: building the error
        has to stay free of side effects, and only the handler knows whether the
        failure is worth writing down.
        """
        self.marker.write_text(f"{self}\n", encoding="utf-8")
