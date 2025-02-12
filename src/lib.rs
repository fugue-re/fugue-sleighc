use std::env;
use std::io;
use std::path::{Path, PathBuf};
use std::process::{Command, ExitStatus, Stdio};

use thiserror::Error;

#[derive(Debug, Error)]
pub enum SleighCompilerError {
    #[error("compilation failed: {0}; {1}")]
    Compile(ExitStatus, String),
    #[error("cannot execute sleighc binary: {0}")]
    Compiler(io::Error),
    #[error("cannot find sleighc binary at `{}`", _0.display())]
    NotFound(PathBuf),
    #[error("input format/file `{}` unsupported", _0.display())]
    UnsupportedInput(PathBuf),
}

#[derive(Debug, Clone)]
pub struct SleighCompiler {
    binary: PathBuf,
    recursive: bool,
    xml_mode: bool,
}

impl SleighCompiler {
    pub fn new() -> Result<Self, SleighCompilerError> {
        let binary = if matches!(env::var("HOST"), Ok(host) if host.contains("windows")) {
            PathBuf::from_iter([env!("OUT_DIR"), "bin", "sleighc.exe"])
        } else {
            PathBuf::from_iter([env!("OUT_DIR"), "bin", "sleighc"])
        };

        Ok(Self {
            binary,
            recursive: false,
            xml_mode: false,
        })
    }

    pub fn xml_mode(&mut self, enabled: bool) -> &mut Self {
        self.xml_mode = enabled;
        self
    }

    pub fn recursive(&mut self, recursive: bool) -> &mut Self {
        self.recursive = recursive;
        self
    }

    fn command(
        &self,
        input: impl AsRef<Path>,
    ) -> Result<(Command, Option<PathBuf>), SleighCompilerError> {
        let mut cmd = Command::new(&self.binary);

        cmd.stderr(Stdio::piped());
        cmd.stdout(Stdio::null());

        if self.xml_mode {
            cmd.arg("-y");
        }

        if self.recursive {
            cmd.arg("-a");
            cmd.arg(input.as_ref());
            return Ok((cmd, None));
        }

        let input = input.as_ref();
        let ninput = if matches!(input.extension(), Some(ext) if ext == "slaspec") {
            input.to_owned()
        } else if let Some(name) = input.file_name() {
            let file = name.to_string_lossy() + ".slaspec".as_ref();
            input.with_file_name(&*file)
        } else {
            return Err(SleighCompilerError::UnsupportedInput(input.to_owned()));
        };

        cmd.arg(input);

        Ok((cmd, Some(ninput)))
    }

    pub fn build_with(
        &self,
        input: impl AsRef<Path>,
        output: impl AsRef<Path>,
    ) -> Result<Option<PathBuf>, SleighCompilerError> {
        let output = output.as_ref();
        let (mut cmd, _ninput) = self.command(input)?;

        cmd.arg(output);

        let outcome = cmd.output().map_err(SleighCompilerError::Compiler)?;
        let status = outcome.status;

        if status.success() {
            Ok((!self.recursive).then(|| {
                if matches!(output.extension(), Some(ext) if ext == "sla") {
                    output.to_owned()
                } else if let Some(name) = output.file_name() {
                    let file = name.to_string_lossy() + ".sla".as_ref();
                    output.with_file_name(&*file)
                } else {
                    output.to_owned()
                }
            }))
        } else {
            let err = String::from_utf8(outcome.stderr).expect("utf8 output");
            Err(SleighCompilerError::Compile(status, err))
        }
    }

    pub fn build(&self, input: impl AsRef<Path>) -> Result<Option<PathBuf>, SleighCompilerError> {
        let (mut cmd, ninput) = self.command(input)?;

        let outcome = cmd.output().map_err(SleighCompilerError::Compiler)?;
        let status = outcome.status;

        if status.success() {
            Ok(ninput.map(|p| p.with_extension("sla")))
        } else {
            let err = String::from_utf8(outcome.stderr).expect("utf8 output");
            Err(SleighCompilerError::Compile(status, err))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn it_works() -> Result<(), Box<dyn std::error::Error>> {
        let output = SleighCompiler::new()?
            .xml_mode(true)
            .build("data/processors/ARM/ARM8_le")?;

        println!("{output:?}");

        let output = SleighCompiler::new()?
            .xml_mode(true)
            .build_with("data/processors/ARM/ARM8_le", "ARM8_le.slip")?;

        println!("{output:?}");

        let output = SleighCompiler::new()?
            .recursive(true)
            .xml_mode(true)
            .build("data/processors/ARM")?;

        println!("{output:?}");

        Ok(())
    }
}
