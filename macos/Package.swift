// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "MacRemote",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "MacRemote", targets: ["MacRemote"])
    ],
    targets: [
        .systemLibrary(name: "CSQLite"),
        .executableTarget(
            name: "MacRemote",
            dependencies: ["CSQLite"]
        )
    ]
)
