// The harness appends these checks to production helpers without CLI dispatch.
// Objects stay in memory. No permissions, fetch, save, or delete calls occur.
func expectFailure(_ operation: () throws -> Void) {
    do {
        try operation()
        fatalError("Expected rejection")
    } catch {}
}

expectFailure { _ = try uniqueReminderMatch([Int]()) }
expectFailure { _ = try uniqueReminderMatch([1, 2]) }
let singleMatch = try uniqueReminderMatch([42])
assert(singleMatch == 42)
expectFailure { _ = try parseReminderMutationArgs(["--id"], update: false) }
expectFailure { _ = try parseReminderMutationArgs(["--id", "one", "--id", "two"], update: false) }
expectFailure { _ = try parseReminderMutationArgs(["--id", "one", "--repeat", "daily"], update: true) }
expectFailure { _ = try parseReminderMutationArgs(["--clear-due", "false"], update: true) }
let parsed = try parseReminderMutationArgs(["--id", "one", "--notes", "", "--clear-due"], update: true)
assert(parsed["notes"] == "" && parsed["clear-due"] == "true")
expectFailure { _ = try ReminderUpdate(["id": "one"]) }
expectFailure { _ = try ReminderUpdate(["priority": "3"]) }
expectFailure { _ = try ReminderUpdate(["title": ""]) }
expectFailure { _ = try ReminderUpdate(["list": ""]) }
expectFailure { _ = try ReminderUpdate(["due": "2026-02-30"]) }
expectFailure { _ = try ReminderUpdate(["due": "2026-09-07 junk"]) }
expectFailure { _ = try ReminderUpdate(["due": "2026-09-07", "clear-due": "true"]) }

let dateOnlyDue = try parseReminderDueDate("2026-09-07")
assert(dateOnlyDue.year == 2026 && dateOnlyDue.month == 9 && dateOnlyDue.day == 7)
assert(dateOnlyDue.hour == nil && dateOnlyDue.minute == nil)
expectFailure { _ = try parseReminderDueDate("2026-02-30") }
let reminder = EKReminder(eventStore: store)
let originalList = EKCalendar(for: .reminder, eventStore: store)
originalList.title = "Inbox"
reminder.calendar = originalList
reminder.title = "Call vendor"
reminder.notes = "PROJECT: Vendor\nKeep all metadata"
reminder.priority = 5
reminder.dueDateComponents = DateComponents(year: 2026, month: 9, day: 7, hour: 16, minute: 30)
let rule = EKRecurrenceRule(recurrenceWith: .weekly, interval: 2, end: nil)
reminder.addRecurrenceRule(rule)
let originalDue = reminder.dueDateComponents
let originalNotes = reminder.notes
let originalRules = reminder.recurrenceRules
let originalId = reminder.calendarItemIdentifier
try ReminderUpdate(["title": "Call supplier"]).apply(to: reminder, destination: nil)
assert(reminder.title == "Call supplier")
assert(reminder.notes == originalNotes)
assert(reminder.priority == 5)
assert(reminder.dueDateComponents == originalDue)
assert(reminder.recurrenceRules == originalRules)
assert(reminder.calendar === originalList)
assert(reminder.calendarItemIdentifier == originalId)
assert(!reminder.isCompleted)
let destination = EKCalendar(for: .reminder, eventStore: store)
destination.title = "@office"
try ReminderUpdate(["list": "@office"]).apply(to: reminder, destination: destination)
assert(reminder.calendar === destination)
assert(reminder.notes == originalNotes && reminder.dueDateComponents == originalDue)
assert(reminder.recurrenceRules == originalRules)
try ReminderUpdate(["due": "2026-09-08"]).apply(to: reminder, destination: nil)
assert(reminder.dueDateComponents?.day == 8)
assert(reminder.dueDateComponents?.hour == nil)
let noon = parseDate("2026-09-08 12:00")!
assert(!isReminderOverdue(reminder.dueDateComponents, now: noon))
assert(isReminderOverdue(reminder.dueDateComponents, now: parseDate("2026-09-09 00:00")!))
try ReminderUpdate(["due": "2026-09-08 10:15"]).apply(to: reminder, destination: nil)
assert(reminder.dueDateComponents?.hour == 10 && reminder.dueDateComponents?.minute == 15)
assert(isReminderOverdue(reminder.dueDateComponents, now: noon))
try ReminderUpdate(["clear-due": "true", "notes": "", "priority": "0"]).apply(to: reminder, destination: nil)
assert(reminder.dueDateComponents == nil && reminder.notes == "" && reminder.priority == 0)
assert(reminder.recurrenceRules == originalRules)
assert(!isReminderOverdue(nil, now: noon))
let info = ReminderInfo(id: "stable-id", title: "Task", list: "Inbox", dueDate: nil,
                        priority: 0, isCompleted: false, notes: nil, isRecurring: false, recurrence: nil)
let json = try JSONSerialization.jsonObject(with: JSONEncoder().encode(info)) as! [String: Any]
assert(json["id"] as? String == "stable-id")
let created = ActionResult(success: true, message: "Created", id: "new-id")
let createdJSON = try JSONSerialization.jsonObject(with: JSONEncoder().encode(created)) as! [String: Any]
assert(createdJSON["id"] as? String == "new-id" && createdJSON["success"] as? Bool == true)
print("Reminder mutation checks passed")
