// Print the id and bounds of Claude Desktop's main window, for `screencapture -l`.
//
// Output: "<windowId> <x> <y> <width> <height>" in points, or exit 1 if Claude has
// no on-screen window. Compiled once by desktop-capture.sh; there is no shell-only
// way to get a window id on macOS.

import CoreGraphics
import Foundation

let owner = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "Claude"
let options: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
let windows = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[String: Any]] ?? []

// The main window is the largest normal-layer window the app owns; menus and
// popovers sit on other layers or are much smaller.
var best: (id: Int, rect: CGRect)?
for window in windows {
    guard (window[kCGWindowOwnerName as String] as? String) == owner,
          (window[kCGWindowLayer as String] as? Int) == 0,
          let id = window[kCGWindowNumber as String] as? Int,
          let boundsDict = window[kCGWindowBounds as String] as? NSDictionary,
          let rect = CGRect(dictionaryRepresentation: boundsDict)
    else { continue }
    if best == nil || rect.width * rect.height > best!.rect.width * best!.rect.height {
        best = (id, rect)
    }
}

guard let found = best else {
    FileHandle.standardError.write("no on-screen window owned by \(owner)\n".data(using: .utf8)!)
    exit(1)
}
print("\(found.id) \(Int(found.rect.minX)) \(Int(found.rect.minY)) \(Int(found.rect.width)) \(Int(found.rect.height))")
