// swift-tools-version:5.10
import PackageDescription

let package = Package(
    name: "Devkit",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(name: "Devkit", path: "Sources/Devkit")
    ]
)
