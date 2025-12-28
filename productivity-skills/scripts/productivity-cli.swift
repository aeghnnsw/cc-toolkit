#!/usr/bin/env swift

import EventKit
import Foundation

// MARK: - JSON Output Helpers

struct CalendarInfo: Codable {
    let name: String
    let type: String
    let color: String?
}

struct EventInfo: Codable {
    let title: String
    let calendar: String
    let startDate: String
    let endDate: String
    let location: String?
    let notes: String?
    let isAllDay: Bool
}

struct ReminderListInfo: Codable {
    let name: String
    let count: Int
}

struct ReminderInfo: Codable {
    let title: String
    let list: String
    let dueDate: String?
    let priority: Int
    let isCompleted: Bool
    let notes: String?
}

struct ActionResult: Codable {
    let success: Bool
    let message: String
}

struct ErrorResponse: Codable {
    let error: String
}

struct SuccessResponse<T: Codable>: Codable {
    let success: Bool
    let data: T
    let count: Int
}

func outputJSON<T: Codable>(_ data: T) {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
    do {
        let jsonData = try encoder.encode(data)
        if let jsonString = String(data: jsonData, encoding: .utf8) {
            print(jsonString)
        } else {
            fputs("{\"error\": \"Failed to encode JSON as UTF-8 string\"}\n", stderr)
            exit(1)
        }
    } catch {
        fputs("{\"error\": \"JSON encoding failed: \(error.localizedDescription)\"}\n", stderr)
        exit(1)
    }
}

func outputError(_ message: String) -> Never {
    outputJSON(ErrorResponse(error: message))
    exit(1)
}

func outputSuccess<T: Codable>(_ data: [T]) {
    outputJSON(SuccessResponse(success: true, data: data, count: data.count))
}

func outputResult(_ success: Bool, _ message: String) {
    outputJSON(ActionResult(success: success, message: message))
    if !success { exit(1) }
}

// MARK: - Date Helpers

let dateFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateFormat = "yyyy-MM-dd HH:mm:ss"
    return formatter
}()

let inputDateFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateFormat = "yyyy-MM-dd HH:mm"
    return formatter
}()

let dateOnlyFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.dateFormat = "yyyy-MM-dd"
    return formatter
}()

func parseDate(_ string: String) -> Date? {
    return inputDateFormatter.date(from: string) ?? dateOnlyFormatter.date(from: string)
}

func startOfDay(_ date: Date) -> Date {
    Calendar.current.startOfDay(for: date)
}

func endOfDay(_ date: Date) -> Date {
    guard let result = Calendar.current.date(byAdding: .day, value: 1, to: startOfDay(date)) else {
        // Fallback: add 24 hours if date arithmetic fails (may be incorrect during DST transitions)
        fputs("Warning: Calendar date arithmetic failed for \(date), using 24-hour fallback\n", stderr)
        return startOfDay(date).addingTimeInterval(86400)
    }
    return result
}

// MARK: - Argument Parsing Helpers

func parseArgs(_ args: [String]) -> [String: String] {
    var result: [String: String] = [:]
    var i = 0
    while i < args.count {
        let arg = args[i]
        if arg.hasPrefix("--") {
            let key = String(arg.dropFirst(2))
            if i + 1 < args.count && !args[i + 1].hasPrefix("--") {
                result[key] = args[i + 1]
                i += 2
            } else {
                result[key] = "true"
                i += 1
            }
        } else {
            i += 1
        }
    }
    return result
}

// MARK: - EventKit Store

let store = EKEventStore()

func requestCalendarAccess() -> (granted: Bool, error: String?) {
    var granted = false
    var accessError: String? = nil
    let semaphore = DispatchSemaphore(value: 0)

    if #available(macOS 14.0, *) {
        store.requestFullAccessToEvents { success, error in
            granted = success
            accessError = error?.localizedDescription
            semaphore.signal()
        }
    } else {
        store.requestAccess(to: .event) { success, error in
            granted = success
            accessError = error?.localizedDescription
            semaphore.signal()
        }
    }

    let timeout = DispatchTime.now() + .seconds(30)
    if semaphore.wait(timeout: timeout) == .timedOut {
        return (false, "Timeout waiting for calendar access permission")
    }
    return (granted, accessError)
}

func requestReminderAccess() -> (granted: Bool, error: String?) {
    var granted = false
    var accessError: String? = nil
    let semaphore = DispatchSemaphore(value: 0)

    if #available(macOS 14.0, *) {
        store.requestFullAccessToReminders { success, error in
            granted = success
            accessError = error?.localizedDescription
            semaphore.signal()
        }
    } else {
        store.requestAccess(to: .reminder) { success, error in
            granted = success
            accessError = error?.localizedDescription
            semaphore.signal()
        }
    }

    let timeout = DispatchTime.now() + .seconds(30)
    if semaphore.wait(timeout: timeout) == .timedOut {
        return (false, "Timeout waiting for reminder access permission")
    }
    return (granted, accessError)
}

// MARK: - Calendar Read Commands

func listCalendars() {
    let access = requestCalendarAccess()
    guard access.granted else {
        let reason = access.error ?? "Unknown reason"
        outputError("Calendar access denied: \(reason)")
    }

    let calendars = store.calendars(for: .event)
    let calendarInfos = calendars.map { cal -> CalendarInfo in
        let typeString: String
        switch cal.type {
        case .local: typeString = "local"
        case .calDAV: typeString = "calDAV"
        case .exchange: typeString = "exchange"
        case .subscription: typeString = "subscription"
        case .birthday: typeString = "birthday"
        @unknown default: typeString = "unknown"
        }
        return CalendarInfo(
            name: cal.title,
            type: typeString,
            color: cal.cgColor?.components?.description
        )
    }
    outputSuccess(calendarInfos)
}

func getEvents(from startDate: Date, to endDate: Date, searchTerm: String? = nil, calendarName: String? = nil) {
    let access = requestCalendarAccess()
    guard access.granted else {
        let reason = access.error ?? "Unknown reason"
        outputError("Calendar access denied: \(reason)")
    }

    var calendars = store.calendars(for: .event)

    if let name = calendarName {
        calendars = calendars.filter { $0.title.lowercased() == name.lowercased() }
        if calendars.isEmpty {
            outputError("Calendar '\(name)' not found")
            return
        }
    }

    let predicate = store.predicateForEvents(withStart: startDate, end: endDate, calendars: calendars)
    var events = store.events(matching: predicate)

    if let term = searchTerm?.lowercased(), !term.isEmpty {
        events = events.filter { $0.title?.lowercased().contains(term) ?? false }
    }

    let eventInfos = events.map { event -> EventInfo in
        EventInfo(
            title: event.title ?? "Untitled",
            calendar: event.calendar.title,
            startDate: dateFormatter.string(from: event.startDate),
            endDate: dateFormatter.string(from: event.endDate),
            location: event.location,
            notes: event.notes,
            isAllDay: event.isAllDay
        )
    }
    outputSuccess(eventInfos)
}

func getTodayEvents() {
    let today = Date()
    getEvents(from: startOfDay(today), to: endOfDay(today))
}

func getWeekEvents() {
    let today = Date()
    guard let weekEnd = Calendar.current.date(byAdding: .day, value: 7, to: today) else {
        outputError("Internal error: Could not calculate week end date")
    }
    getEvents(from: startOfDay(today), to: endOfDay(weekEnd))
}

func searchEvents(_ term: String) {
    let today = Date()
    guard let yearEnd = Calendar.current.date(byAdding: .day, value: 365, to: today) else {
        outputError("Internal error: Could not calculate search end date")
    }
    getEvents(from: startOfDay(today), to: endOfDay(yearEnd), searchTerm: term)
}

func getEventsOnDate(_ dateStr: String, calendarName: String?) {
    guard let date = parseDate(dateStr) else {
        outputError("Invalid date format. Use yyyy-MM-dd")
        return
    }
    getEvents(from: startOfDay(date), to: endOfDay(date), calendarName: calendarName)
}

func getEventsInRange(_ startStr: String, _ endStr: String, calendarName: String?) {
    guard let startDate = parseDate(startStr) else {
        outputError("Invalid start date format. Use yyyy-MM-dd")
    }
    guard let endDate = parseDate(endStr) else {
        outputError("Invalid end date format. Use yyyy-MM-dd")
    }
    guard startDate <= endDate else {
        outputError("Start date must be before or equal to end date")
    }
    getEvents(from: startOfDay(startDate), to: endOfDay(endDate), calendarName: calendarName)
}

// MARK: - Calendar Write Commands

func createEvent(_ args: [String: String]) {
    let access = requestCalendarAccess()
    guard access.granted else {
        let reason = access.error ?? "Unknown reason"
        outputError("Calendar access denied: \(reason)")
    }

    guard let title = args["title"] else {
        outputError("Missing required argument: --title")
        return
    }

    guard let calendarName = args["calendar"] else {
        outputError("Missing required argument: --calendar")
        return
    }

    guard let startStr = args["start"] else {
        outputError("Missing required argument: --start (format: yyyy-MM-dd HH:mm)")
        return
    }

    guard let startDate = parseDate(startStr) else {
        outputError("Invalid start date format. Use yyyy-MM-dd HH:mm")
        return
    }

    let calendars = store.calendars(for: .event)
    guard let calendar = calendars.first(where: { $0.title.lowercased() == calendarName.lowercased() }) else {
        outputError("Calendar '\(calendarName)' not found")
        return
    }

    let event = EKEvent(eventStore: store)
    event.calendar = calendar
    event.title = title
    event.startDate = startDate

    // Handle all-day events
    if args["allday"] == "true" {
        event.isAllDay = true
        guard let allDayEnd = Calendar.current.date(byAdding: .day, value: 1, to: startOfDay(startDate)) else {
            outputError("Internal error: Could not calculate all-day event end date")
        }
        event.endDate = allDayEnd
    } else if let endStr = args["end"], let endDate = parseDate(endStr) {
        event.endDate = endDate
    } else {
        // Default to 1 hour duration
        guard let defaultEnd = Calendar.current.date(byAdding: .hour, value: 1, to: startDate) else {
            outputError("Internal error: Could not calculate default event end date")
        }
        event.endDate = defaultEnd
    }

    if let location = args["location"] {
        event.location = location
    }

    if let notes = args["notes"] {
        event.notes = notes
    }

    // Add alarm if specified (minutes before)
    if let alarmStr = args["alarm"] {
        guard let alarmMinutes = Int(alarmStr), alarmMinutes >= 0 else {
            outputError("Invalid alarm value: '\(alarmStr)' - must be a non-negative number of minutes")
        }
        let alarm = EKAlarm(relativeOffset: TimeInterval(-alarmMinutes * 60))
        event.addAlarm(alarm)
    }

    do {
        try store.save(event, span: .thisEvent)
        outputResult(true, "Event '\(title)' created successfully")
    } catch {
        outputError("Failed to create event: \(error.localizedDescription)")
    }
}

func deleteEvent(_ args: [String: String]) {
    let access = requestCalendarAccess()
    guard access.granted else {
        let reason = access.error ?? "Unknown reason"
        outputError("Calendar access denied: \(reason)")
    }

    guard let title = args["title"] else {
        outputError("Missing required argument: --title")
        return
    }

    guard let dateStr = args["date"] else {
        outputError("Missing required argument: --date (format: yyyy-MM-dd)")
        return
    }

    guard let date = parseDate(dateStr) else {
        outputError("Invalid date format. Use yyyy-MM-dd")
        return
    }

    var calendars = store.calendars(for: .event)
    if let calendarName = args["calendar"] {
        calendars = calendars.filter { $0.title.lowercased() == calendarName.lowercased() }
    }

    let predicate = store.predicateForEvents(withStart: startOfDay(date), end: endOfDay(date), calendars: calendars)
    let events = store.events(matching: predicate).filter { $0.title?.lowercased() == title.lowercased() }

    if events.isEmpty {
        outputError("No event found with title '\(title)' on \(dateStr)")
        return
    }

    var deletedCount = 0
    var failedCount = 0
    var lastError: String? = nil

    for event in events {
        do {
            try store.remove(event, span: .thisEvent)
            deletedCount += 1
        } catch {
            failedCount += 1
            lastError = error.localizedDescription
        }
    }

    if failedCount > 0 && deletedCount == 0 {
        outputError("Failed to delete event(s): \(lastError ?? "Unknown error")")
    } else if failedCount > 0 {
        outputResult(true, "Deleted \(deletedCount) event(s) with title '\(title)', but \(failedCount) failed: \(lastError ?? "Unknown error")")
    } else {
        outputResult(true, "Deleted \(deletedCount) event(s) with title '\(title)'")
    }
}

// MARK: - Reminder Read Commands

func listReminderLists() {
    let access = requestReminderAccess()
    guard access.granted else {
        let reason = access.error ?? "Unknown reason"
        outputError("Reminder access denied: \(reason)")
    }

    let calendars = store.calendars(for: .reminder)

    var listInfos: [ReminderListInfo] = []
    let lock = NSLock()
    let group = DispatchGroup()

    for cal in calendars {
        group.enter()
        let predicate = store.predicateForReminders(in: [cal])
        store.fetchReminders(matching: predicate) { reminders in
            let count = reminders?.filter { !$0.isCompleted }.count ?? 0
            let info = ReminderListInfo(name: cal.title, count: count)
            lock.lock()
            listInfos.append(info)
            lock.unlock()
            group.leave()
        }
    }

    group.wait()
    outputSuccess(listInfos.sorted { $0.name < $1.name })
}

func fetchReminders(predicate: NSPredicate, filter: ((EKReminder) -> Bool)? = nil) -> [ReminderInfo] {
    var reminderInfos: [ReminderInfo] = []
    let semaphore = DispatchSemaphore(value: 0)

    store.fetchReminders(matching: predicate) { reminders in
        guard let reminders = reminders else {
            semaphore.signal()
            return
        }

        let filtered = filter != nil ? reminders.filter(filter!) : reminders

        reminderInfos = filtered.map { reminder -> ReminderInfo in
            var dueDateStr: String? = nil
            if let dueDate = reminder.dueDateComponents?.date {
                dueDateStr = dateFormatter.string(from: dueDate)
            }

            return ReminderInfo(
                title: reminder.title ?? "Untitled",
                list: reminder.calendar.title,
                dueDate: dueDateStr,
                priority: reminder.priority,
                isCompleted: reminder.isCompleted,
                notes: reminder.notes
            )
        }
        semaphore.signal()
    }

    semaphore.wait()
    return reminderInfos
}

func getTodayReminders() {
    let access = requestReminderAccess()
    guard access.granted else {
        let reason = access.error ?? "Unknown reason"
        outputError("Reminder access denied: \(reason)")
    }

    let calendars = store.calendars(for: .reminder)
    let predicate = store.predicateForReminders(in: calendars)

    let today = startOfDay(Date())
    let tomorrow = endOfDay(Date())

    let reminders = fetchReminders(predicate: predicate) { reminder in
        guard !reminder.isCompleted,
              let dueDate = reminder.dueDateComponents?.date else {
            return false
        }
        return dueDate >= today && dueDate < tomorrow
    }

    outputSuccess(reminders)
}

func getIncompleteReminders(listName: String?) {
    let access = requestReminderAccess()
    guard access.granted else {
        let reason = access.error ?? "Unknown reason"
        outputError("Reminder access denied: \(reason)")
    }

    var calendars = store.calendars(for: .reminder)

    if let name = listName {
        calendars = calendars.filter { $0.title.lowercased() == name.lowercased() }
        if calendars.isEmpty {
            outputError("Reminder list '\(name)' not found")
            return
        }
    }

    let predicate = store.predicateForIncompleteReminders(withDueDateStarting: nil, ending: nil, calendars: calendars)
    let reminders = fetchReminders(predicate: predicate)
    outputSuccess(reminders)
}

func getOverdueReminders() {
    let access = requestReminderAccess()
    guard access.granted else {
        let reason = access.error ?? "Unknown reason"
        outputError("Reminder access denied: \(reason)")
    }

    let calendars = store.calendars(for: .reminder)
    let now = Date()
    let predicate = store.predicateForIncompleteReminders(withDueDateStarting: nil, ending: now, calendars: calendars)
    let reminders = fetchReminders(predicate: predicate)
    outputSuccess(reminders)
}

// MARK: - Reminder Write Commands

func createReminder(_ args: [String: String]) {
    let access = requestReminderAccess()
    guard access.granted else {
        let reason = access.error ?? "Unknown reason"
        outputError("Reminder access denied: \(reason)")
    }

    guard let title = args["title"] else {
        outputError("Missing required argument: --title")
        return
    }

    guard let listName = args["list"] else {
        outputError("Missing required argument: --list")
        return
    }

    let calendars = store.calendars(for: .reminder)
    guard let calendar = calendars.first(where: { $0.title.lowercased() == listName.lowercased() }) else {
        outputError("Reminder list '\(listName)' not found")
        return
    }

    let reminder = EKReminder(eventStore: store)
    reminder.calendar = calendar
    reminder.title = title

    if let dueDateStr = args["due"] {
        guard let dueDate = parseDate(dueDateStr) else {
            outputError("Invalid due date format: '\(dueDateStr)' - use yyyy-MM-dd or yyyy-MM-dd HH:mm")
        }
        reminder.dueDateComponents = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: dueDate)
    }

    if let priorityStr = args["priority"] {
        guard let priority = Int(priorityStr) else {
            outputError("Invalid priority value: '\(priorityStr)' - must be a number")
        }
        // Priority: 0=none, 1=high, 5=medium, 9=low
        let validPriorities = [0, 1, 5, 9]
        guard validPriorities.contains(priority) else {
            outputError("Invalid priority: \(priority) - valid values are 0 (none), 1 (high), 5 (medium), 9 (low)")
        }
        reminder.priority = priority
    }

    if let notes = args["notes"] {
        reminder.notes = notes
    }

    do {
        try store.save(reminder, commit: true)
        outputResult(true, "Reminder '\(title)' created successfully")
    } catch {
        outputError("Failed to create reminder: \(error.localizedDescription)")
    }
}

func completeReminder(_ args: [String: String]) {
    let access = requestReminderAccess()
    guard access.granted else {
        let reason = access.error ?? "Unknown reason"
        outputError("Reminder access denied: \(reason)")
    }

    guard let title = args["title"] else {
        outputError("Missing required argument: --title")
        return
    }

    var calendars = store.calendars(for: .reminder)
    if let listName = args["list"] {
        calendars = calendars.filter { $0.title.lowercased() == listName.lowercased() }
        if calendars.isEmpty {
            outputError("Reminder list '\(listName)' not found")
            return
        }
    }

    let predicate = store.predicateForReminders(in: calendars)
    let semaphore = DispatchSemaphore(value: 0)
    var foundReminder: EKReminder? = nil

    store.fetchReminders(matching: predicate) { reminders in
        foundReminder = reminders?.first { $0.title?.lowercased() == title.lowercased() && !$0.isCompleted }
        semaphore.signal()
    }
    semaphore.wait()

    guard let reminder = foundReminder else {
        outputError("Incomplete reminder '\(title)' not found")
        return
    }

    reminder.isCompleted = true

    do {
        try store.save(reminder, commit: true)
        outputResult(true, "Reminder '\(title)' marked as complete")
    } catch {
        outputError("Failed to complete reminder: \(error.localizedDescription)")
    }
}

func uncompleteReminder(_ args: [String: String]) {
    let access = requestReminderAccess()
    guard access.granted else {
        let reason = access.error ?? "Unknown reason"
        outputError("Reminder access denied: \(reason)")
    }

    guard let title = args["title"] else {
        outputError("Missing required argument: --title")
        return
    }

    var calendars = store.calendars(for: .reminder)
    if let listName = args["list"] {
        calendars = calendars.filter { $0.title.lowercased() == listName.lowercased() }
        if calendars.isEmpty {
            outputError("Reminder list '\(listName)' not found")
            return
        }
    }

    let predicate = store.predicateForReminders(in: calendars)
    let semaphore = DispatchSemaphore(value: 0)
    var foundReminder: EKReminder? = nil

    store.fetchReminders(matching: predicate) { reminders in
        foundReminder = reminders?.first { $0.title?.lowercased() == title.lowercased() && $0.isCompleted }
        semaphore.signal()
    }
    semaphore.wait()

    guard let reminder = foundReminder else {
        outputError("Completed reminder '\(title)' not found")
        return
    }

    reminder.isCompleted = false

    do {
        try store.save(reminder, commit: true)
        outputResult(true, "Reminder '\(title)' marked as incomplete")
    } catch {
        outputError("Failed to uncomplete reminder: \(error.localizedDescription)")
    }
}

func deleteReminder(_ args: [String: String]) {
    let access = requestReminderAccess()
    guard access.granted else {
        let reason = access.error ?? "Unknown reason"
        outputError("Reminder access denied: \(reason)")
    }

    guard let title = args["title"] else {
        outputError("Missing required argument: --title")
        return
    }

    var calendars = store.calendars(for: .reminder)
    if let listName = args["list"] {
        calendars = calendars.filter { $0.title.lowercased() == listName.lowercased() }
        if calendars.isEmpty {
            outputError("Reminder list '\(listName)' not found")
            return
        }
    }

    let predicate = store.predicateForReminders(in: calendars)
    let semaphore = DispatchSemaphore(value: 0)
    var foundReminder: EKReminder? = nil

    store.fetchReminders(matching: predicate) { reminders in
        foundReminder = reminders?.first { $0.title?.lowercased() == title.lowercased() }
        semaphore.signal()
    }
    semaphore.wait()

    guard let reminder = foundReminder else {
        outputError("Reminder '\(title)' not found")
        return
    }

    do {
        try store.remove(reminder, commit: true)
        outputResult(true, "Reminder '\(title)' deleted")
    } catch {
        outputError("Failed to delete reminder: \(error.localizedDescription)")
    }
}

func createReminderList(_ name: String) {
    let access = requestReminderAccess()
    guard access.granted else {
        let reason = access.error ?? "Unknown reason"
        outputError("Reminder access denied: \(reason)")
    }

    let calendar = EKCalendar(for: .reminder, eventStore: store)
    calendar.title = name

    // Use the default source for reminders
    guard let source = store.defaultCalendarForNewReminders()?.source else {
        outputError("No default reminder source available")
        return
    }
    calendar.source = source

    do {
        try store.saveCalendar(calendar, commit: true)
        outputResult(true, "Reminder list '\(name)' created")
    } catch {
        outputError("Failed to create reminder list: \(error.localizedDescription)")
    }
}

// MARK: - Main

func printUsage() {
    let usage = """
    Usage: productivity-cli <command> [arguments]

    Calendar Commands:
      calendars list                          List all calendars
      calendars today                         Get today's events
      calendars week                          Get this week's events
      calendars search <term>                 Search events by title
      calendars date <yyyy-MM-dd> [--calendar <name>]
                                              Get events on a specific date
      calendars range <start> <end> [--calendar <name>]
                                              Get events in date range
      calendars create --title <title> --calendar <name> --start <yyyy-MM-dd HH:mm>
                       [--end <yyyy-MM-dd HH:mm>] [--location <loc>] [--notes <text>]
                       [--allday] [--alarm <minutes>]
                                              Create a new event
      calendars delete --title <title> --date <yyyy-MM-dd> [--calendar <name>]
                                              Delete an event

    Reminder Commands:
      reminders lists                         List all reminder lists
      reminders today                         Get reminders due today
      reminders incomplete [list]             Get incomplete reminders
      reminders overdue                       Get overdue reminders
      reminders create --title <title> --list <name>
                       [--due <yyyy-MM-dd HH:mm>] [--priority <0|1|5|9>] [--notes <text>]
                                              Create a new reminder
      reminders complete --title <title> [--list <name>]
                                              Mark reminder as complete
      reminders uncomplete --title <title> [--list <name>]
                                              Mark reminder as incomplete
      reminders delete --title <title> [--list <name>]
                                              Delete a reminder
      reminders create-list <name>            Create a new reminder list

    Priority values: 0=none, 1=high, 5=medium, 9=low
    """
    print(usage)
}

let args = Array(CommandLine.arguments.dropFirst())

guard args.count >= 2 else {
    printUsage()
    exit(1)
}

let category = args[0]
let command = args[1]
let remainingArgs = Array(args.dropFirst(2))
let parsedArgs = parseArgs(remainingArgs)

switch (category, command) {
// Calendar read commands
case ("calendars", "list"):
    listCalendars()
case ("calendars", "today"):
    getTodayEvents()
case ("calendars", "week"):
    getWeekEvents()
case ("calendars", "search"):
    guard remainingArgs.count >= 1 else {
        outputError("Missing search term")
    }
    searchEvents(remainingArgs[0])
case ("calendars", "date"):
    guard remainingArgs.count >= 1 else {
        outputError("Missing date argument")
    }
    getEventsOnDate(remainingArgs[0], calendarName: parsedArgs["calendar"])
case ("calendars", "range"):
    guard remainingArgs.count >= 2 else {
        outputError("Missing start and/or end date arguments")
    }
    getEventsInRange(remainingArgs[0], remainingArgs[1], calendarName: parsedArgs["calendar"])

// Calendar write commands
case ("calendars", "create"):
    createEvent(parsedArgs)
case ("calendars", "delete"):
    deleteEvent(parsedArgs)

// Reminder read commands
case ("reminders", "lists"):
    listReminderLists()
case ("reminders", "today"):
    getTodayReminders()
case ("reminders", "incomplete"):
    let listName = remainingArgs.first { !$0.hasPrefix("--") }
    getIncompleteReminders(listName: listName)
case ("reminders", "overdue"):
    getOverdueReminders()

// Reminder write commands
case ("reminders", "create"):
    createReminder(parsedArgs)
case ("reminders", "complete"):
    completeReminder(parsedArgs)
case ("reminders", "uncomplete"):
    uncompleteReminder(parsedArgs)
case ("reminders", "delete"):
    deleteReminder(parsedArgs)
case ("reminders", "create-list"):
    guard remainingArgs.count >= 1 else {
        outputError("Missing list name")
    }
    createReminderList(remainingArgs[0])

default:
    printUsage()
    exit(1)
}
