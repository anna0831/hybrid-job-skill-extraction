/**
 * xlsx_lite.js — Zero-dependency, 100% offline .xlsx reader & 4-sheet writer.
 * Uses native CompressionStream / DecompressionStream ('deflate-raw') in Chrome & Node.
 */
(function (root) {
  "use strict";

  const CRC_TABLE = (() => {
    const t = new Uint32Array(256);
    for (let i = 0; i < 256; i++) {
      let c = i;
      for (let k = 0; k < 8; k++) c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
      t[i] = c >>> 0;
    }
    return t;
  })();

  function crc32(bytes) {
    let c = 0xffffffff;
    for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  }

  async function inflateRaw(bytes) {
    if (typeof DecompressionStream !== "undefined") {
      const ds = new DecompressionStream("deflate-raw");
      const stream = new Blob([bytes]).stream().pipeThrough(ds);
      return new Uint8Array(await new Response(stream).arrayBuffer());
    }
    throw new Error("目前瀏覽器不支援 DecompressionStream('deflate-raw')");
  }

  async function deflateRaw(bytes) {
    if (typeof CompressionStream !== "undefined") {
      const cs = new CompressionStream("deflate-raw");
      const stream = new Blob([bytes]).stream().pipeThrough(cs);
      return new Uint8Array(await new Response(stream).arrayBuffer());
    }
    throw new Error("目前瀏覽器不支援 CompressionStream('deflate-raw')");
  }

  function u16(dv, o) { return dv.getUint16(o, true); }
  function u32(dv, o) { return dv.getUint32(o, true); }

  async function unzipEntries(arrayBuffer) {
    const bytes = new Uint8Array(arrayBuffer);
    const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    // Find End of Central Directory (0x06054b50)
    let eocd = -1;
    for (let i = bytes.length - 22; i >= Math.max(0, bytes.length - 65557); i--) {
      if (u32(dv, i) === 0x06054b50) { eocd = i; break; }
    }
    if (eocd < 0) throw new Error("無效的 .xlsx / ZIP 檔案（找不到 EOCD）。");
    const cdCount = u16(dv, eocd + 10);
    const cdOffset = u32(dv, eocd + 16);
    const dec = new TextDecoder("utf-8");
    const entries = new Map();
    let ptr = cdOffset;
    for (let i = 0; i < cdCount; i++) {
      if (u32(dv, ptr) !== 0x02014b50) break;
      const method = u16(dv, ptr + 10);
      const compSize = u32(dv, ptr + 20);
      const nameLen = u16(dv, ptr + 28);
      const extraLen = u16(dv, ptr + 30);
      const commentLen = u16(dv, ptr + 32);
      const localOffset = u32(dv, ptr + 42);
      const name = dec.decode(bytes.subarray(ptr + 46, ptr + 46 + nameLen));
      ptr += 46 + nameLen + extraLen + commentLen;

      const lNameLen = u16(dv, localOffset + 26);
      const lExtraLen = u16(dv, localOffset + 28);
      const dataStart = localOffset + 30 + lNameLen + lExtraLen;
      const rawSlice = bytes.subarray(dataStart, dataStart + compSize);
      let data;
      if (method === 0) data = rawSlice;
      else if (method === 8) data = await inflateRaw(rawSlice);
      else continue;
      entries.set(name, data);
    }
    return entries;
  }

  function colToIndex(ref) {
    let col = 0;
    for (let i = 0; i < ref.length; i++) {
      const ch = ref.charCodeAt(i);
      if (ch >= 65 && ch <= 90) col = col * 26 + (ch - 64);
      else if (ch >= 97 && ch <= 122) col = col * 26 + (ch - 96);
      else break;
    }
    return col - 1;
  }

  function decodeXmlEntities(s) {
    return s
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&quot;/g, '"')
      .replace(/&apos;/g, "'")
      .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(parseInt(n, 10)))
      .replace(/&#x([0-9a-fA-F]+);/g, (_, h) => String.fromCodePoint(parseInt(h, 16)))
      .replace(/&amp;/g, "&");
  }

  function parseSharedStrings(xmlText) {
    const out = [];
    const siRe = /<si\b[^>]*>([\s\S]*?)<\/si>/g;
    let m;
    while ((m = siRe.exec(xmlText)) !== null) {
      const inner = m[1];
      const tRe = /<t\b[^>]*>([\s\S]*?)<\/t>/g;
      let tm;
      let buf = "";
      while ((tm = tRe.exec(inner)) !== null) {
        buf += decodeXmlEntities(tm[1]);
      }
      out.push(buf);
    }
    return out;
  }

  function parseWorksheetRows(xmlText, sharedStrings) {
    const rows = [];
    const rowRe = /<row\b[^>]*>([\s\S]*?)<\/row>/g;
    let rm;
    while ((rm = rowRe.exec(xmlText)) !== null) {
      const rowXml = rm[1];
      const rowArr = [];
      const cellRe = /<c\b([^>]*)(?:\/>|>([\s\S]*?)<\/c>)/g;
      let cm;
      while ((cm = cellRe.exec(rowXml)) !== null) {
        const attrs = cm[1];
        const body = cm[2] || "";
        const refM = /\br="([A-Za-z]+\d+)"/.exec(attrs);
        const typeM = /\bt="([^"]+)"/.exec(attrs);
        const colIdx = refM ? colToIndex(refM[1]) : rowArr.length;
        const cType = typeM ? typeM[1] : "";
        let val = "";
        if (cType === "inlineStr") {
          const tRe = /<t\b[^>]*>([\s\S]*?)<\/t>/g;
          let tm;
          while ((tm = tRe.exec(body)) !== null) val += decodeXmlEntities(tm[1]);
        } else {
          const vM = /<v\b[^>]*>([\s\S]*?)<\/v>/.exec(body);
          if (vM) {
            const rawV = decodeXmlEntities(vM[1]);
            if (cType === "s") {
              const sIdx = parseInt(rawV, 10);
              val = sharedStrings[sIdx] !== undefined ? sharedStrings[sIdx] : "";
            } else if (cType === "b") {
              val = rawV === "1" ? "TRUE" : "FALSE";
            } else {
              val = rawV;
            }
          }
        }
        while (rowArr.length <= colIdx) rowArr.push("");
        rowArr[colIdx] = val;
      }
      if (rowArr.some((v) => String(v).trim() !== "")) rows.push(rowArr);
    }
    return rows;
  }

  async function readXlsxRecords(arrayBuffer) {
    const entries = await unzipEntries(arrayBuffer);
    const dec = new TextDecoder("utf-8");
    let sharedStrings = [];
    if (entries.has("xl/sharedStrings.xml")) {
      sharedStrings = parseSharedStrings(dec.decode(entries.get("xl/sharedStrings.xml")));
    }
    let sheetPath = "xl/worksheets/sheet1.xml";
    if (!entries.has(sheetPath)) {
      for (const k of entries.keys()) {
        if (/^xl\/worksheets\/sheet\d+\.xml$/.test(k)) { sheetPath = k; break; }
      }
    }
    if (!entries.has(sheetPath)) throw new Error(".xlsx 檔案內找不到工作表資料。");
    const rows = parseWorksheetRows(dec.decode(entries.get(sheetPath)), sharedStrings);
    if (rows.length === 0) return [];
    const headers = rows[0].map((h) => String(h || "").trim());
    const records = [];
    for (let i = 1; i < rows.length; i++) {
      const row = rows[i];
      const rec = {};
      for (let c = 0; c < headers.length; c++) {
        if (headers[c]) rec[headers[c]] = row[c] !== undefined ? row[c] : "";
      }
      records.push(rec);
    }
    return records;
  }

  function xmlEsc(val) {
    return String(val == null ? "" : val)
      .replace(/[\x00-\x08\x0B\x0C\x0E-\x1F]/g, "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&apos;");
  }

  function colName(idx) {
    let n = idx + 1;
    let s = "";
    while (n > 0) {
      const r = (n - 1) % 26;
      s = String.fromCharCode(65 + r) + s;
      n = Math.floor((n - 1) / 26);
    }
    return s;
  }

  function buildWorksheetXml(headers, rows) {
    const lines = [
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
      '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
      "<sheetData>",
    ];
    const allRows = [headers, ...rows];
    for (let r = 0; r < allRows.length; r++) {
      const row = allRows[r];
      const rNum = r + 1;
      let cells = "";
      for (let c = 0; c < headers.length; c++) {
        const ref = `${colName(c)}${rNum}`;
        const v = row[c];
        if (typeof v === "number" && Number.isFinite(v)) {
          cells += `<c r="${ref}"><v>${v}</v></c>`;
        } else if (typeof v === "boolean") {
          cells += `<c r="${ref}" t="b"><v>${v ? 1 : 0}</v></c>`;
        } else {
          cells += `<c r="${ref}" t="inlineStr"><is><t xml:space="preserve">${xmlEsc(v)}</t></is></c>`;
        }
      }
      lines.push(`<row r="${rNum}">${cells}</row>`);
    }
    lines.push("</sheetData></worksheet>");
    return lines.join("");
  }

  async function buildZip(files) {
    const enc = new TextEncoder();
    const localParts = [];
    const cdParts = [];
    let offset = 0;

    for (const f of files) {
      const nameBytes = enc.encode(f.name);
      const rawBytes = typeof f.content === "string" ? enc.encode(f.content) : f.content;
      const crc = crc32(rawBytes);
      const compBytes = await deflateRaw(rawBytes);

      const lh = new Uint8Array(30 + nameBytes.length);
      const ldv = new DataView(lh.buffer);
      ldv.setUint32(0, 0x04034b50, true);
      ldv.setUint16(4, 20, true);
      ldv.setUint16(6, 0x0800, true); // UTF-8
      ldv.setUint16(8, 8, true); // deflate
      ldv.setUint32(14, crc, true);
      ldv.setUint32(18, compBytes.length, true);
      ldv.setUint32(22, rawBytes.length, true);
      ldv.setUint16(26, nameBytes.length, true);
      lh.set(nameBytes, 30);

      localParts.push(lh, compBytes);

      const ch = new Uint8Array(46 + nameBytes.length);
      const cdv = new DataView(ch.buffer);
      cdv.setUint32(0, 0x02014b50, true);
      cdv.setUint16(4, 20, true);
      cdv.setUint16(6, 20, true);
      cdv.setUint16(8, 0x0800, true);
      cdv.setUint16(10, 8, true);
      cdv.setUint32(16, crc, true);
      cdv.setUint32(20, compBytes.length, true);
      cdv.setUint32(24, rawBytes.length, true);
      cdv.setUint16(28, nameBytes.length, true);
      cdv.setUint32(42, offset, true);
      ch.set(nameBytes, 46);
      cdParts.push(ch);

      offset += lh.length + compBytes.length;
    }

    const cdStart = offset;
    let cdSize = 0;
    for (const p of cdParts) cdSize += p.length;

    const eocd = new Uint8Array(22);
    const edv = new DataView(eocd.buffer);
    edv.setUint32(0, 0x06054b50, true);
    edv.setUint16(8, files.length, true);
    edv.setUint16(10, files.length, true);
    edv.setUint32(12, cdSize, true);
    edv.setUint32(16, cdStart, true);

    const totalLen = offset + cdSize + eocd.length;
    const out = new Uint8Array(totalLen);
    let pos = 0;
    for (const p of localParts) { out.set(p, pos); pos += p.length; }
    for (const p of cdParts) { out.set(p, pos); pos += p.length; }
    out.set(eocd, pos);
    return out;
  }

  async function writeMultiSheetXlsx(sheets) {
    // sheets: [{ name: string, headers: string[], rows: any[][] }]
    const contentTypes = [
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
      '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
      '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
      '<Default Extension="xml" ContentType="application/xml"/>',
      '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
      ...sheets.map((_, i) => `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`),
      "</Types>",
    ].join("");

    const rootRels =
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
      '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
      '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>' +
      "</Relationships>";

    const wbXml =
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
      '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">' +
      "<sheets>" +
      sheets.map((s, i) => `<sheet name="${xmlEsc(s.name)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`).join("") +
      "</sheets></workbook>";

    const wbRels =
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
      '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
      sheets.map((_, i) => `<Relationship Id="rId${i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`).join("") +
      "</Relationships>";

    const files = [
      { name: "[Content_Types].xml", content: contentTypes },
      { name: "_rels/.rels", content: rootRels },
      { name: "xl/workbook.xml", content: wbXml },
      { name: "xl/_rels/workbook.xml.rels", content: wbRels },
      ...sheets.map((s, i) => ({
        name: `xl/worksheets/sheet${i + 1}.xml`,
        content: buildWorksheetXml(s.headers, s.rows),
      })),
    ];

    return await buildZip(files);
  }

  root.XlsxLite = {
    readXlsxRecords,
    writeMultiSheetXlsx,
  };
})(typeof window !== "undefined" ? window : globalThis);

