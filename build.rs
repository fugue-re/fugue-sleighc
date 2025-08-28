fn main() {
    cmake::Config::new("vendored")
        .define("BUILD_COMPILER", "ON")
        .define("BUILD_DECOMPILER", "OFF")
        .build();
}
