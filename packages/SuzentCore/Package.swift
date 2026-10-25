// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "SuzentCore",
    platforms: [.iOS(.v17), .macOS(.v14)],
    products: [.library(name: "SuzentCore", targets: ["SuzentCore"])],
    targets: [
        .target(name: "SuzentCore", resources: [.process("Resources")]),
        .testTarget(name: "SuzentCoreTests", dependencies: ["SuzentCore"])
    ]
)
