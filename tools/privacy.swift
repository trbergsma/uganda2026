// Haalt persoonlijke gegevens uit foto's, zonder ze opnieuw te comprimeren:
//   - de GPS-locatie
//   - de namen van mensen die Apple Foto's in de foto heeft herkend
// Datum, draaiing en de rest van de gegevens blijven staan.
//
// Gebruik: swift tools/privacy.swift foto1.jpeg foto2.jpeg ...
// Per foto waar een locatie uit is gehaald komt er een regel op stdout:
//     naam<TAB>breedtegraad<TAB>lengtegraad
import Foundation
import ImageIO

let namenPad = "Iptc4xmpExt:PersonInImage" as CFString

for pad in CommandLine.arguments.dropFirst() {
    let url = URL(fileURLWithPath: pad)
    guard let bron = CGImageSourceCreateWithURL(url as CFURL, nil),
          let type = CGImageSourceGetType(bron),
          let eigenschappen = CGImageSourceCopyPropertiesAtIndex(bron, 0, nil) as? [CFString: Any],
          let origineel = CGImageSourceCopyMetadataAtIndex(bron, 0, nil),
          let metadata = CGImageMetadataCreateMutableCopy(origineel)
    else { continue }

    let gps = eigenschappen[kCGImagePropertyGPSDictionary] as? [CFString: Any] ?? [:]
    let heeftNamen = CGImageMetadataCopyTagWithPath(metadata, nil, namenPad) != nil
    if gps.isEmpty && !heeftNamen { continue }
    if heeftNamen { CGImageMetadataRemoveTagWithPath(metadata, nil, namenPad) }

    // Zonder expliciete metadata laat ImageIO alles weg; geef die dus mee en sluit alleen GPS uit.
    let tijdelijk = url.appendingPathExtension("tmp")
    guard let doel = CGImageDestinationCreateWithURL(tijdelijk as CFURL, type, 1, nil) else { continue }
    let opties = [kCGImageDestinationMetadata: metadata,
                  kCGImageDestinationMergeMetadata: false,
                  kCGImageMetadataShouldExcludeGPS: true] as [CFString: Any] as CFDictionary
    guard CGImageDestinationCopyImageSource(doel, bron, opties, nil),
          (try? FileManager.default.replaceItemAt(url, withItemAt: tijdelijk)) != nil
    else {
        try? FileManager.default.removeItem(at: tijdelijk)
        FileHandle.standardError.write(Data("LET OP: privacygegevens niet verwijderd uit \(url.lastPathComponent)\n".utf8))
        continue
    }
    if !gps.isEmpty {
        var lat = gps[kCGImagePropertyGPSLatitude] as? Double ?? 0
        var lon = gps[kCGImagePropertyGPSLongitude] as? Double ?? 0
        if gps[kCGImagePropertyGPSLatitudeRef] as? String == "S" { lat = -lat }
        if gps[kCGImagePropertyGPSLongitudeRef] as? String == "W" { lon = -lon }
        print("\(url.lastPathComponent)\t\(lat)\t\(lon)")
    }
}
