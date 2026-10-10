//! IoStoreの索引から必要なチャンクだけを読み取る。索引・物理配置の一致は要求しない。
use crate::{fail, no_links, read_small, unavailable, Chunk, Result};
use std::{fs::{self, File}, io::{Read, Seek, SeekFrom}, path::Path};

fn bytes(data: &[u8], at: usize, len: usize) -> Result<&[u8]> {
    data.get(at..at.checked_add(len).ok_or("索引の範囲が不正です。")?)
        .ok_or_else(|| "索引が途中で切れています。".into())
}
fn le(data: &[u8], at: usize, len: usize) -> Result<u64> {
    Ok(bytes(data, at, len)?.iter().rev().fold(0, |n, b| (n << 8) | u64::from(*b)))
}
fn be(data: &[u8]) -> u64 { data.iter().fold(0, |n, b| (n << 8) | u64::from(*b)) }

struct Index<'a> {
    data: &'a [u8], entries: usize, offsets: usize, blocks: usize, block_count: usize,
    methods: usize, method_count: usize, method_width: usize, block_size: u64,
    partition_size: u64, partition_count: u64, encrypted: bool,
}
impl<'a> Index<'a> {
    fn parse(data: &'a [u8]) -> Result<Self> {
        if bytes(data, 0, 16)? != b"-==--==--==--==-" { return fail("IoStore索引の識別情報が不正です。"); }
        let version = bytes(data, 16, 1)?[0];
        if !(3..=8).contains(&version) { return unavailable(); }
        if le(data, 20, 4)? != 144 || le(data, 32, 4)? != 12 { return fail("索引の構造が不正です。"); }
        bytes(data, 0, 144)?;
        let entries = le(data, 24, 4)? as usize;
        let block_count = le(data, 28, 4)? as usize;
        let method_count = le(data, 36, 4)? as usize;
        let method_width = le(data, 40, 4)? as usize;
        let block_size = le(data, 44, 4)?;
        let partition_count = le(data, 52, 4)?;
        let partition_size = le(data, 88, 8)?;
        if entries > 2_000_000 || block_count > 4_000_000 || method_count > 255 || method_width > 256
            || (method_count > 0 && method_width == 0) || block_size == 0 || block_size > 1_048_576
            || partition_size == 0 || partition_count == 0 {
            return fail("索引のサイズが不正です。");
        }
        let seeds = if version >= 4 { le(data, 84, 4)? as usize } else { 0 };
        let overflow = if version >= 5 { le(data, 96, 4)? as usize } else { 0 };
        if seeds > 2_000_000 || overflow > 2_000_000 { return fail("索引の件数が不正です。"); }
        let offsets = 144 + entries * 12;
        let blocks = offsets + entries * 10 + (seeds + overflow) * 4;
        let methods = blocks + block_count * 12;
        bytes(data, 144, methods + method_count * method_width - 144)?;
        Ok(Self { data, entries, offsets, blocks, block_count, methods, method_count, method_width,
            block_size, partition_size, partition_count, encrypted: data[80] & 2 != 0 })
    }

    fn locate(&self, id: &[u8]) -> Result<Option<(u64, u64)>> {
        let mut found = None;
        for i in 0..self.entries {
            if &self.data[144 + i * 12..144 + (i + 1) * 12] != id { continue; }
            // 同じIDが複数ある場合は古い方を推測して使わない。
            if found.is_some() { return unavailable(); }
            let entry = &self.data[self.offsets + i * 10..self.offsets + (i + 1) * 10];
            found = Some((be(&entry[..5]), be(&entry[5..])));
        }
        Ok(found)
    }

    fn extract(&self, toc: &Path, offset: u64, size: u64) -> Result<Vec<u8>> {
        if self.encrypted { return unavailable(); }
        let end = offset.checked_add(size).ok_or("チャンク範囲が不正です。")?;
        let first = offset / self.block_size;
        let last = (end - 1) / self.block_size;
        if last >= self.block_count as u64 || last - first > 1024 { return fail("チャンクのブロック範囲が不正です。"); }
        let mut output = Vec::with_capacity(size as usize);
        for i in first..=last {
            let at = self.blocks + i as usize * 12;
            let physical = le(self.data, at, 5)?;
            let compressed_size = le(self.data, at + 5, 3)? as usize;
            let decoded_size = le(self.data, at + 8, 3)? as usize;
            let method = self.data[at + 11] as usize;
            if compressed_size == 0 || compressed_size > 1_048_576 || decoded_size == 0 || decoded_size as u64 > self.block_size {
                return fail("対象ブロックのサイズが不正です。");
            }
            let partition = physical / self.partition_size;
            let position = physical % self.partition_size;
            if partition >= self.partition_count || compressed_size as u64 > self.partition_size - position {
                return fail("対象ブロックの分割位置が不正です。");
            }
            let path = if partition == 0 { toc.with_extension("ucas") } else {
                let stem = toc.file_stem().and_then(|s| s.to_str()).ok_or("コンテナ名が不正です。")?;
                toc.with_file_name(format!("{stem}_s{partition}.ucas"))
            };
            no_links(&path)?;
            let mut file = File::open(&path)?;
            if position.checked_add(compressed_size as u64).ok_or("対象範囲が不正です。")? > file.metadata()?.len() {
                return fail("ゲームファイルが途中で切れています。");
            }
            file.seek(SeekFrom::Start(position))?;
            let mut compressed = vec![0; compressed_size];
            file.read_exact(&mut compressed)?;
            let decoded = if method == 0 {
                if compressed_size != decoded_size { return fail("非圧縮ブロックのサイズが不正です。"); }
                compressed
            } else {
                if method > self.method_count { return fail("圧縮方式の参照が不正です。"); }
                let raw_name = &self.data[self.methods + (method - 1) * self.method_width..self.methods + method * self.method_width];
                let name = raw_name.split(|b| *b == 0).next().unwrap_or_default();
                if !name.eq_ignore_ascii_case(b"oodle") { return unavailable(); }
                let mut decoded = vec![0; decoded_size];
                // 入力は更新され得るので、上限付きで展開して対象チャンク自体を照合する。
                match oozextract::Extractor::new().read_from_slice(&compressed, &mut decoded) {
                    Ok(count) if count == decoded_size => decoded,
                    _ => return unavailable(),
                }
            };
            let start = if i == first { (offset % self.block_size) as usize } else { 0 };
            let count = ((end - i * self.block_size).min(self.block_size) as usize)
                .checked_sub(start).ok_or("チャンクの切り出し範囲が不正です。")?;
            output.extend_from_slice(bytes(&decoded, start, count)?);
        }
        Ok(output)
    }
}

pub fn read_chunks(paks: &Path, chunks: &[Chunk]) -> Result<Vec<Vec<u8>>> {
    let ids: Vec<Vec<u8>> = chunks.iter().map(|c| crate::hex(&c.chunk_id)).collect::<Result<_>>()?;
    let mut locations = vec![None; chunks.len()];
    let mut paths = Vec::new();
    for entry in fs::read_dir(paks)? {
        let path = entry?.path();
        let name = path.file_name().and_then(|s| s.to_str()).unwrap_or_default().to_ascii_lowercase();
        if name.starts_with("pakchunk") && name.ends_with(".utoc") { paths.push(path); }
    }
    paths.sort();
    if paths.len() > 256 { return fail("コンテナ数が上限を超えています。"); }
    // 追加の公式コンテナにも同じIDがあれば、ロード優先順位を推測せず基本版へ戻す。
    for path in &paths {
        let data = read_small(path, 64_000_000)?;
        let index = Index::parse(&data)?;
        for (i, id) in ids.iter().enumerate() {
            if let Some((offset, size)) = index.locate(id)? {
                if locations[i].is_some() { return unavailable(); }
                locations[i] = Some((path.clone(), offset, size));
            }
        }
    }
    let mut output = Vec::new();
    for (chunk, location) in chunks.iter().zip(locations) {
        let Some((path, offset, size)) = location else { return unavailable(); };
        if size != chunk.size as u64 { return unavailable(); }
        let data = read_small(&path, 64_000_000)?;
        let index = Index::parse(&data)?;
        let content = index.extract(&path, offset, size)?;
        if crate::digest(&content) != chunk.sha256 { return unavailable(); }
        output.push(content);
    }
    Ok(output)
}
