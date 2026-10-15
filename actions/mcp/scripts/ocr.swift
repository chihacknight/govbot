// Print the text macOS's Vision framework reads in an image, one line per region.
//
// desktop-capture.sh uses it to read a permission prompt before answering it, so
// only govbot's own tool prompts are ever approved.

import Foundation
import Vision

guard CommandLine.arguments.count > 1,
      let url = Optional(URL(fileURLWithPath: CommandLine.arguments[1])),
      let source = CGImageSourceCreateWithURL(url as CFURL, nil),
      let image = CGImageSourceCreateImageAtIndex(source, 0, nil)
else {
    FileHandle.standardError.write("usage: ocr <image.png>\n".data(using: .utf8)!)
    exit(2)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
try VNImageRequestHandler(cgImage: image).perform([request])
for observation in request.results ?? [] {
    if let line = observation.topCandidates(1).first?.string { print(line) }
}
