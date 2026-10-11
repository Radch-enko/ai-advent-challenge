class DailyJournalError(RuntimeError):
    pass


class DailyJournalConflictError(DailyJournalError):
    pass


class DailyJournalStorageError(DailyJournalError):
    pass
