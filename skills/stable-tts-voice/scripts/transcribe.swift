// stable-tts-voice · https://github.com/Bf190t/qwen3-tts-stable-voice
// Idea and workflow: Bf190t. SPDX-License-Identifier: MIT
// Transcribes every .wav in a folder with macOS 26's on-device recognizer (SpeechAnalyzer +
// SpeechTranscriber) and writes FOLDER/asr.tsv ("file<TAB>text"), which measure_voice.py reads.
//
//   swiftc -O transcribe.swift -o "$SCRATCH/transcribe"     (once; macOS 26 SDK, Command Line Tools)
//   "$SCRATCH/transcribe" runs/现在 [zh_CN|en_US]
//   "$SCRATCH/transcribe" --install [zh_CN|en_US]           (ask the user first: the system downloads it)
//
// It needs the system speech model for that language. If it is missing, `--install` asks macOS to
// download and install it (AssetInventory). Recognition itself runs on the Mac; nothing is uploaded.
import AVFoundation
import Foundation
import Speech

@available(macOS 26.0, *)
func collect(_ module: SpeechTranscriber) async throws -> String {
    var text = ""
    for try await result in module.results where result.isFinal { text += String(result.text.characters) }
    return text
}

@available(macOS 26.0, *)
func transcribe(_ url: URL, locale: Locale) async throws -> String {
    let module = SpeechTranscriber(locale: locale, preset: .transcription)
    let analyzer = SpeechAnalyzer(modules: [module])
    async let text = collect(module)
    let audio = try AVAudioFile(forReading: url)
    if let last = try await analyzer.analyzeSequence(from: audio) { try await analyzer.finalizeAndFinish(through: last) }
    else { await analyzer.cancelAndFinishNow() }
    return try await text
}

let arguments = CommandLine.arguments
guard arguments.count >= 2 else { print("usage: transcribe FOLDER [zh_CN|en_US]  |  transcribe --install [zh_CN|en_US]"); exit(2) }
if arguments[1] == "--install" {
    let locale = Locale(identifier: arguments.count > 2 ? arguments[2] : "zh_CN")
    let finished = DispatchSemaphore(value: 0)
    var code: Int32 = 0
    Task {
        defer { finished.signal() }
        guard #available(macOS 26.0, *) else { print("needs macOS 26"); code = 1; return }
        let module = SpeechTranscriber(locale: locale, preset: .transcription)
        do {
            if let request = try await AssetInventory.assetInstallationRequest(supporting: [module]) {
                print("downloading the \(locale.identifier) speech model…")
                try await request.downloadAndInstall()
                print("installed the \(locale.identifier) speech model")
            } else {
                print("the \(locale.identifier) speech model is already installed")
            }
        } catch {
            print("could not install the \(locale.identifier) speech model: \(error)"); code = 1
        }
    }
    finished.wait()
    exit(code)
}
let folder = URL(fileURLWithPath: arguments[1])
let locale = Locale(identifier: arguments.count > 2 ? arguments[2] : "zh_CN")
let files = (try? FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil))?
    .filter { $0.pathExtension == "wav" }.sorted { $0.lastPathComponent < $1.lastPathComponent } ?? []
let done = DispatchSemaphore(value: 0)
var status: Int32 = 0
Task {
    defer { done.signal() }
    guard #available(macOS 26.0, *) else { print("needs macOS 26"); status = 1; return }
    let installed = await SpeechTranscriber.installedLocales
    guard installed.contains(where: { $0.identifier(.bcp47) == locale.identifier(.bcp47) }) else {
        print("the \(locale.identifier) speech model is not installed on this Mac; run: transcribe --install \(locale.identifier)"); status = 1; return
    }
    var lines: [String] = []
    for file in files {
        let text = (try? await transcribe(file, locale: locale)) ?? "<error>"
        let clean = text.replacingOccurrences(of: "\t", with: " ").replacingOccurrences(of: "\n", with: " ")
        lines.append(file.lastPathComponent + "\t" + clean)
        print(lines.last!)
    }
    try? (lines.joined(separator: "\n") + "\n").write(to: folder.appendingPathComponent("asr.tsv"), atomically: true, encoding: .utf8)
}
done.wait()
exit(status)
