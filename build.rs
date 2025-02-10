fn main() -> Result<(), Box<dyn std::error::Error>> {
    cmake::build("vendored");
    Ok(())
}
