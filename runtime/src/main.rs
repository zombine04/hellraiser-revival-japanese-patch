//! 対応版の必要な範囲だけを読み、原本を変更せず統合IoStoreを生成する。
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::{fs::{self, File, OpenOptions}, io::{Read, Seek, SeekFrom, Write}, path::{Path, PathBuf}};
const STEM: &str = "Hellraiser_Revival_Japanese_P";
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Recipe { schema_version: u32, toc_sha256: String, seed_sha256: String, blocks: Vec<Block>, outputs: Vec<Output> }
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Block { offset: u64, compressed_size: usize, size: usize, sha256: String, decoded_sha256: String, compression: String }
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Output { name: String, size: usize, sha256: String, ops: Vec<Op> }
#[derive(Deserialize)]
#[serde(untagged, deny_unknown_fields)]
enum Op { Copy { copy: [usize; 3] }, Data { data: String } }
fn fail<T>(message: &str) -> Result<T> { Err(message.into()) }
fn digest(bytes: &[u8]) -> String { format!("{:x}", Sha256::digest(bytes)) }
fn matches(bytes: &[u8], expected: &str) -> Result<()> {
    if expected.len() != 64 || digest(bytes) != expected { return fail("必要なファイルのハッシュが一致しません。"); }
    Ok(())
}
fn no_links(path: &Path) -> Result<()> {
    for part in path.ancestors() {
        if let Ok(meta) = fs::symlink_metadata(part) {
            #[cfg(windows)] { use std::os::windows::fs::MetadataExt; if meta.file_attributes() & 0x400 != 0 { return fail("リンクを含む場所は使用できません。"); } }
            if meta.file_type().is_symlink() { return fail("リンクを含む場所は使用できません。"); }
        }
    }
    Ok(())
}
fn read_small(path: &Path, limit: u64) -> Result<Vec<u8>> {
    no_links(path)?;
    let file = File::open(path)?;
    if file.metadata()?.len() > limit { return fail("入力ファイルが上限を超えています。"); }
    let mut bytes = Vec::new(); file.take(limit + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 > limit { return fail("入力ファイルが上限を超えています。"); }
    Ok(bytes)
}
fn hex(text: &str) -> Result<Vec<u8>> {
    if text.len() % 2 != 0 || text.len() > 131072 || !text.is_ascii() { return fail("変更手順の形式が不正です。"); }
    (0..text.len()).step_by(2).map(|i| Ok(u8::from_str_radix(&text[i..i+2],16)?)).collect()
}
fn assemble(output: &Output, sources: &[Vec<u8>]) -> Result<Vec<u8>> {
    if output.size > 2_000_000 || output.ops.len() > 20_000 { return fail("生成サイズが上限を超えています。"); }
    let mut result = Vec::with_capacity(output.size);
    for op in &output.ops {
        match op {
            Op::Copy { copy: [source, offset, length] } => {
                let input = sources.get(*source).ok_or("参照元が不正です。")?;
                let end = offset.checked_add(*length).ok_or("参照範囲が不正です。")?;
                let part = input.get(*offset..end).ok_or("参照範囲が不正です。")?;
                if result.len() + part.len() > output.size { return fail("生成サイズが不正です。"); }
                result.extend_from_slice(part);
            }
            Op::Data { data } => {
                let bytes = hex(data)?;
                if result.len() + bytes.len() > output.size { return fail("生成サイズが不正です。"); }
                result.extend_from_slice(&bytes);
            }
        }
    }
    if result.len() != output.size { return fail("生成サイズが一致しません。"); }
    matches(&result, &output.sha256)?;
    Ok(result)
}
fn generate(package: &Path, paks: &Path, destination: &Path) -> Result<()> {
    for path in [package, paks, destination] { no_links(path)?; }
    let recipe: Recipe = serde_json::from_slice(&read_small(&package.join("ui-patch.json"), 2_000_000)?)?;
    if recipe.schema_version != 1 || recipe.blocks.len() != 3 || recipe.outputs.len() != 2 { return fail("変更手順の形式が不正です。"); }
    let toc = read_small(&paks.join("pakchunk0-Windows.utoc"),64_000_000)?;
    matches(&toc, &recipe.toc_sha256)?;
    let seed = read_small(&package.join(format!("{STEM}.ucas")), 2_000_000)?;
    matches(&seed, &recipe.seed_sha256)?;
    let original = paks.join("pakchunk0-Windows.ucas"); no_links(&original)?;
    let mut source = File::open(&original)?; let source_size = source.metadata()?.len();
    let mut sources = vec![seed];
    for block in &recipe.blocks {
        if block.size == 0 || block.size > 1_000_000 || block.compressed_size == 0 || block.compressed_size > 1_000_000 { return fail("対象範囲が不正です。"); }
        if block.offset.checked_add(block.compressed_size as u64).ok_or("対象範囲が不正です。")? > source_size { return fail("ゲームファイルが不足しています。"); }
        source.seek(SeekFrom::Start(block.offset))?;
        let mut compressed = vec![0;block.compressed_size]; source.read_exact(&mut compressed)?;
        // 展開前に既知の圧縮データと照合し、不明な入力をデコーダーに渡さない。
        matches(&compressed, &block.sha256)?;
        let bytes = match block.compression.as_str() {
            "oodle" => { let mut decoded=vec![0;block.size]; let count=oozextract::Extractor::new().read_from_slice(&compressed,&mut decoded)?; if count != block.size { return fail("展開サイズが一致しません。"); } decoded },
            "none" if compressed.len() == block.size => compressed,
            _ => return fail("対応していない圧縮形式です。"),
        };
        matches(&bytes,&block.decoded_sha256)?; sources.push(bytes);
    }
    let mut prepared = Vec::new();
    for (output, extension) in recipe.outputs.iter().zip(["utoc","ucas"]) {
        if output.name != format!("{STEM}.{extension}") { return fail("生成先の名前が不正です。"); }
        prepared.push((destination.join(&output.name),assemble(output,&sources)?));
    }
    // 両方の生成・照合が成功するまで書き出さない。既存ファイルは上書きしない。
    for (path, _) in &prepared { no_links(path)?; if path.exists() { return fail("生成先に既存ファイルがあります。"); } }
    for (path, bytes) in prepared { OpenOptions::new().write(true).create_new(true).open(path)?.write_all(&bytes)?; }
    Ok(())
}
fn main() {
    let args: Vec<PathBuf> = std::env::args_os().skip(1).map(PathBuf::from).collect();
    std::panic::set_hook(Box::new(|_| {}));
    let succeeded = std::panic::catch_unwind(|| -> Result<()> {
        if args.len()!=3 { return fail("使用法: GeneratePatch 配布フォルダー Paksフォルダー 出力フォルダー"); }
        generate(&args[0],&args[1],&args[2])
    }).map(|r|r.is_ok()).unwrap_or(false);
    if !succeeded { eprintln!("統合パッチの生成を中止しました。対応版・ファイルの整合性・書き込み権限を確認してください。"); std::process::exit(1); }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn bounds_and_digest() {
        let sources=vec![b"abcdef".to_vec()];
        let mut out=Output{name:String::new(),size:4,sha256:digest(b"bcXY"),ops:vec![Op::Copy{copy:[0,1,2]},Op::Data{data:"5859".into()}]};
        assert_eq!(assemble(&out,&sources).unwrap(),b"bcXY");
        out.ops[0]=Op::Copy{copy:[0,usize::MAX,2]};assert!(assemble(&out,&sources).is_err());
        out.ops[0]=Op::Copy{copy:[1,0,2]};assert!(assemble(&out,&sources).is_err());
        out.ops[0]=Op::Copy{copy:[0,5,2]};assert!(assemble(&out,&sources).is_err());
    }
    #[test] fn self_authored_oodle_stream() {
        let payload=b"our own decoder test data";
        let mut encoded=vec![0xcc,6];encoded.extend_from_slice(payload);
        let mut decoded=vec![0;payload.len()];
        assert_eq!(oozextract::Extractor::new().read_from_slice(&encoded,&mut decoded).unwrap(),payload.len());
        assert_eq!(decoded,payload);
    }
}
