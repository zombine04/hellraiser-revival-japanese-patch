//! 対象UIチャンクだけを照合し、原本を変更せず統合IoStoreを生成する。
mod iostore;
use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::{fs::{self, File, OpenOptions}, io::{Read, Write}, path::{Path, PathBuf}};
const STEM: &str = "Hellraiser_Revival_Japanese_P";
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Recipe { schema_version: u32, seed_sha256: String, chunks: Vec<Chunk>, outputs: Vec<Output> }
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Chunk { chunk_id: String, size: usize, sha256: String }
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Output { name: String, size: usize, sha256: String, ops: Vec<Op> }
#[derive(Deserialize)]
#[serde(untagged, deny_unknown_fields)]
enum Op { Copy { copy: [usize; 3] }, Data { data: String } }
fn fail<T>(message: &str) -> Result<T> { Err(message.into()) }
#[derive(Debug)]
struct UiUnavailable;
impl std::fmt::Display for UiUnavailable {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result { f.write_str("対象UI資産の互換性を確認できません。") }
}
impl std::error::Error for UiUnavailable {}
fn unavailable<T>() -> Result<T> { Err(Box::new(UiUnavailable)) }
fn valid_hash(text: &str) -> bool { text.len() == 64 && text.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)) }
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
    if recipe.schema_version != 2 || recipe.chunks.len() != 3 || recipe.outputs.len() != 2 || !valid_hash(&recipe.seed_sha256) { return fail("変更手順の形式が不正です。"); }
    let seed = read_small(&package.join(format!("{STEM}.ucas")), 2_000_000)?;
    matches(&seed, &recipe.seed_sha256)?;
    let mut lengths = vec![seed.len()];
    let mut ids = std::collections::HashSet::new();
    for chunk in &recipe.chunks {
        if chunk.chunk_id.len() != 24 || hex(&chunk.chunk_id)?.len() != 12 || !ids.insert(chunk.chunk_id.to_ascii_lowercase())
            || chunk.size == 0 || chunk.size > 1_000_000 || !valid_hash(&chunk.sha256) { return fail("対象資産の情報が不正です。"); }
        lengths.push(chunk.size);
    }
    // 壊れた配布手順を互換性不一致として見逃さないよう、原本を読む前に全命令を検査。
    let mut literal_size = 0;
    for (output, extension) in recipe.outputs.iter().zip(["utoc", "ucas"]) {
        if output.name != format!("{STEM}.{extension}") || output.size == 0 || output.size > 2_000_000
            || output.ops.len() > 20_000 || !valid_hash(&output.sha256) { return fail("生成情報が不正です。"); }
        let mut size = 0usize;
        for op in &output.ops {
            let count = match op {
                Op::Copy { copy: [source, start, count] } => {
                    let length = lengths.get(*source).ok_or("参照元が不正です。")?;
                    if *count == 0 || start.checked_add(*count).ok_or("参照範囲が不正です。")? > *length { return fail("参照範囲が不正です。"); }
                    *count
                },
                Op::Data { data } => { let n = hex(data)?.len(); literal_size += n; n },
            };
            size = size.checked_add(count).ok_or("生成サイズが不正です。")?;
        }
        if size != output.size || literal_size > 4096 { return fail("生成サイズが不正です。"); }
    }
    let mut sources = vec![seed];
    sources.extend(iostore::read_chunks(paks, &recipe.chunks)?);
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
    let result = std::panic::catch_unwind(|| -> Result<()> {
        if args.len()!=3 { return fail("使用法: GeneratePatch 配布フォルダー Paksフォルダー 出力フォルダー"); }
        generate(&args[0],&args[1],&args[2])
    });
    match result {
        Ok(Ok(())) => {},
        // 2だけを基本日本語化への切り替えに使う。I/O・手順・出力の不整合は1。
        Ok(Err(error)) if error.is::<UiUnavailable>() => std::process::exit(2),
        _ => { eprintln!("統合パッチの生成を中止しました。ファイルの整合性・書き込み権限を確認してください。"); std::process::exit(1); },
    }
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
