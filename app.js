const TAG_END = 0;
const TAG_BYTE = 1;
const TAG_SHORT = 2;
const TAG_INT = 3;
const TAG_LONG = 4;
const TAG_FLOAT = 5;
const TAG_DOUBLE = 6;
const TAG_BYTE_ARRAY = 7;
const TAG_STRING = 8;
const TAG_LIST = 9;
const TAG_COMPOUND = 10;
const TAG_INT_ARRAY = 11;
const TAG_LONG_ARRAY = 12;

const els = {
  form: document.querySelector("#converterForm"),
  file: document.querySelector("#schematicFile"),
  fileName: document.querySelector("#fileName"),
  sourcePack: document.querySelector("#sourcePack"),
  targetPack: document.querySelector("#targetPack"),
  unmappedMode: document.querySelector("#unmappedMode"),
  compressionMode: document.querySelector("#compressionMode"),
  swapButton: document.querySelector("#swapButton"),
  convertButton: document.querySelector("#convertButton"),
  mappingCount: document.querySelector("#mappingCount"),
  knownCount: document.querySelector("#knownCount"),
  changedCount: document.querySelector("#changedCount"),
  statusBox: document.querySelector("#statusBox"),
  resultsSection: document.querySelector("#resultsSection"),
  reportSummary: document.querySelector("#reportSummary"),
  reportDetails: document.querySelector("#reportDetails"),
  saveReportButton: document.querySelector("#saveReportButton"),
  mappingTable: document.querySelector("#mappingTable"),
  mappingLabel: document.querySelector("#mappingLabel"),
  mappingSearch: document.querySelector("#mappingSearch"),
};

let lastReport = null;

class NbtReader {
  constructor(buffer) {
    this.bytes = new Uint8Array(buffer);
    this.view = new DataView(buffer);
    this.pos = 0;
  }

  ensure(size) {
    if (this.pos + size > this.bytes.length) {
      throw new Error("NBT tronqué: fin de fichier inattendue");
    }
  }

  readBytes(size) {
    this.ensure(size);
    const out = this.bytes.slice(this.pos, this.pos + size);
    this.pos += size;
    return out;
  }

  u8() {
    this.ensure(1);
    return this.bytes[this.pos++];
  }

  i8() {
    this.ensure(1);
    return this.view.getInt8(this.pos++);
  }

  i16() {
    this.ensure(2);
    const value = this.view.getInt16(this.pos, false);
    this.pos += 2;
    return value;
  }

  u16() {
    this.ensure(2);
    const value = this.view.getUint16(this.pos, false);
    this.pos += 2;
    return value;
  }

  i32() {
    this.ensure(4);
    const value = this.view.getInt32(this.pos, false);
    this.pos += 4;
    return value;
  }

  i64() {
    this.ensure(8);
    const value = this.view.getBigInt64(this.pos, false);
    this.pos += 8;
    return value;
  }

  f32() {
    this.ensure(4);
    const value = this.view.getFloat32(this.pos, false);
    this.pos += 4;
    return value;
  }

  f64() {
    this.ensure(8);
    const value = this.view.getFloat64(this.pos, false);
    this.pos += 8;
    return value;
  }

  string() {
    const size = this.u16();
    const raw = this.readBytes(size);
    return new TextDecoder().decode(raw);
  }

  namedTag() {
    const type = this.u8();
    if (type === TAG_END) {
      return { type, name: "", tag: { type, value: null } };
    }
    const name = this.string();
    return { type, name, tag: { type, value: this.payload(type) } };
  }

  payload(type) {
    if (type === TAG_BYTE) return this.i8();
    if (type === TAG_SHORT) return this.i16();
    if (type === TAG_INT) return this.i32();
    if (type === TAG_LONG) return this.i64();
    if (type === TAG_FLOAT) return this.f32();
    if (type === TAG_DOUBLE) return this.f64();
    if (type === TAG_BYTE_ARRAY) {
      const size = this.i32();
      return new Uint8Array(this.readBytes(size));
    }
    if (type === TAG_STRING) return this.string();
    if (type === TAG_LIST) {
      const childType = this.u8();
      const size = this.i32();
      const children = [];
      for (let i = 0; i < size; i += 1) {
        children.push({ type: childType, value: this.payload(childType) });
      }
      return { childType, children };
    }
    if (type === TAG_COMPOUND) {
      const items = [];
      while (true) {
        const childType = this.u8();
        if (childType === TAG_END) return items;
        const childName = this.string();
        items.push([childName, { type: childType, value: this.payload(childType) }]);
      }
    }
    if (type === TAG_INT_ARRAY) {
      const size = this.i32();
      return Array.from({ length: size }, () => this.i32());
    }
    if (type === TAG_LONG_ARRAY) {
      const size = this.i32();
      return Array.from({ length: size }, () => this.i64());
    }
    throw new Error(`Type NBT non supporté: ${type}`);
  }
}

class NbtWriter {
  constructor() {
    this.parts = [];
    this.length = 0;
    this.encoder = new TextEncoder();
  }

  push(bytes) {
    this.parts.push(bytes);
    this.length += bytes.length;
  }

  one(value) {
    this.push(Uint8Array.of(value & 0xff));
  }

  dataView(size, callback) {
    const bytes = new Uint8Array(size);
    const view = new DataView(bytes.buffer);
    callback(view);
    this.push(bytes);
  }

  i8(value) {
    this.dataView(1, (view) => view.setInt8(0, value));
  }

  i16(value) {
    this.dataView(2, (view) => view.setInt16(0, value, false));
  }

  i32(value) {
    this.dataView(4, (view) => view.setInt32(0, value, false));
  }

  i64(value) {
    this.dataView(8, (view) => view.setBigInt64(0, BigInt(value), false));
  }

  f32(value) {
    this.dataView(4, (view) => view.setFloat32(0, value, false));
  }

  f64(value) {
    this.dataView(8, (view) => view.setFloat64(0, value, false));
  }

  string(value) {
    const raw = this.encoder.encode(value);
    this.i16(raw.length);
    this.push(raw);
  }

  namedTag(name, tag) {
    this.one(tag.type);
    if (tag.type === TAG_END) return;
    this.string(name);
    this.payload(tag);
  }

  payload(tag) {
    const { type, value } = tag;
    if (type === TAG_BYTE) this.i8(value);
    else if (type === TAG_SHORT) this.i16(value);
    else if (type === TAG_INT) this.i32(value);
    else if (type === TAG_LONG) this.i64(value);
    else if (type === TAG_FLOAT) this.f32(value);
    else if (type === TAG_DOUBLE) this.f64(value);
    else if (type === TAG_BYTE_ARRAY) {
      this.i32(value.length);
      this.push(value);
    } else if (type === TAG_STRING) {
      this.string(value);
    } else if (type === TAG_LIST) {
      this.one(value.childType);
      this.i32(value.children.length);
      for (const child of value.children) this.payload(child);
    } else if (type === TAG_COMPOUND) {
      for (const [childName, child] of value) this.namedTag(childName, child);
      this.one(TAG_END);
    } else if (type === TAG_INT_ARRAY) {
      this.i32(value.length);
      value.forEach((item) => this.i32(item));
    } else if (type === TAG_LONG_ARRAY) {
      this.i32(value.length);
      value.forEach((item) => this.i64(item));
    } else {
      throw new Error(`Type NBT non supporté: ${type}`);
    }
  }

  bytes() {
    const out = new Uint8Array(this.length);
    let offset = 0;
    for (const part of this.parts) {
      out.set(part, offset);
      offset += part.length;
    }
    return out;
  }
}

function compoundGet(compound, name) {
  return compound.value.find(([childName]) => childName === name)?.[1] ?? null;
}

function compoundSet(compound, name, tag) {
  const index = compound.value.findIndex(([childName]) => childName === name);
  if (index >= 0) compound.value[index] = [name, tag];
  else compound.value.push([name, tag]);
}

function compoundRemove(compound, name) {
  compound.value = compound.value.filter(([childName]) => childName !== name);
}

function makeMap(source, target) {
  return `${source}:${target}`;
}

function getActiveEntries() {
  return window.SCHEMATIC_DATA.maps[makeMap(els.sourcePack.value, els.targetPack.value)] ?? [];
}

function getConversionMap() {
  const map = new Map();
  for (const entry of getActiveEntries()) map.set(entry.from, entry.to);
  return map;
}

function getKnownSet(pack) {
  return new Set(window.SCHEMATIC_DATA.knownIds[pack] ?? []);
}

function setStatus(message, tone = "") {
  els.statusBox.textContent = message;
  els.statusBox.className = `status-box ${tone}`.trim();
}

function updatePackControls() {
  if (els.sourcePack.value === els.targetPack.value) {
    els.targetPack.value = els.sourcePack.value === "nationsglory" ? "earthquest" : "nationsglory";
  }
  const entries = getActiveEntries();
  els.mappingCount.textContent = String(entries.length);
  els.knownCount.textContent = String((window.SCHEMATIC_DATA.knownIds[els.sourcePack.value] ?? []).length);
  els.mappingLabel.textContent = `${labelPack(els.sourcePack.value)} vers ${labelPack(els.targetPack.value)}`;
  renderMappingTable();
}

function labelPack(pack) {
  return pack === "nationsglory" ? "NationsGlory" : "EarthQuest";
}

function renderMappingTable() {
  const query = els.mappingSearch.value.trim().toLowerCase();
  const entries = getActiveEntries().filter((entry) => {
    if (!query) return true;
    return [entry.sourceNames, entry.targetNames, `${entry.from}:0`, `${entry.to}:0`]
      .join(" ")
      .toLowerCase()
      .includes(query);
  });
  const visible = entries.slice(0, 250);
  els.mappingTable.innerHTML = visible
    .map(
      (entry) => `
        <tr>
          <td>${escapeHtml(entry.sourceNames)}</td>
          <td><code>${entry.from}:0</code></td>
          <td>${escapeHtml(entry.targetNames)}</td>
          <td><code>${entry.to}:0</code></td>
        </tr>
      `,
    )
    .join("");
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function transformBuffer(buffer, format, mode) {
  const streamName = mode === "decompress" ? "DecompressionStream" : "CompressionStream";
  if (!(streamName in window)) {
    throw new Error(`${streamName} n'est pas disponible dans ce navigateur.`);
  }
  const streamClass = window[streamName];
  const stream = new Blob([buffer]).stream().pipeThrough(new streamClass(format));
  return await new Response(stream).arrayBuffer();
}

async function decodeSchematic(file) {
  const input = await file.arrayBuffer();
  const bytes = new Uint8Array(input);
  if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
    return { compression: "gzip", buffer: await transformBuffer(input, "gzip", "decompress") };
  }
  if (bytes[0] === 0x78) {
    try {
      return { compression: "deflate", buffer: await transformBuffer(input, "deflate", "decompress") };
    } catch {
      return { compression: "raw", buffer: input };
    }
  }
  return { compression: "raw", buffer: input };
}

async function encodeSchematic(rawBytes, compression) {
  if (compression === "raw") return rawBytes;
  return await transformBuffer(rawBytes, compression, "compress");
}

function parseRoot(buffer) {
  const reader = new NbtReader(buffer);
  const { type, name, tag } = reader.namedTag();
  if (type !== TAG_COMPOUND) throw new Error("Le root tag du schematic n'est pas un compound NBT.");
  return { name, tag };
}

function writeRoot(name, tag) {
  const writer = new NbtWriter();
  writer.namedTag(name, tag);
  return writer.bytes();
}

function getBlockId(blocks, addBlocks, index) {
  const low = blocks[index] & 0xff;
  if (!addBlocks) return low;
  const packed = addBlocks[index >> 1] & 0xff;
  const high = index % 2 === 0 ? packed & 0x0f : (packed >> 4) & 0x0f;
  return low | (high << 8);
}

function setBlockId(blocks, addBlocks, index, blockId) {
  blocks[index] = blockId & 0xff;
  const high = (blockId >> 8) & 0x0f;
  const packed = addBlocks[index >> 1] & 0xff;
  addBlocks[index >> 1] = index % 2 === 0 ? (packed & 0xf0) | high : (packed & 0x0f) | (high << 4);
}

function convertRoot(rootTag, conversionMap, knownIds, unmappedMode) {
  const blocksTag = compoundGet(rootTag, "Blocks");
  const dataTag = compoundGet(rootTag, "Data");
  const addTag = compoundGet(rootTag, "AddBlocks");
  if (!blocksTag || blocksTag.type !== TAG_BYTE_ARRAY) throw new Error("Tag Blocks absent ou invalide.");
  if (!dataTag || dataTag.type !== TAG_BYTE_ARRAY) throw new Error("Tag Data absent ou invalide.");

  const blocks = blocksTag.value;
  const data = dataTag.value;
  if (blocks.length !== data.length) {
    throw new Error(`Tailles Blocks/Data incohérentes: ${blocks.length} != ${data.length}.`);
  }

  const addBlocks = addTag?.type === TAG_BYTE_ARRAY ? addTag.value : null;
  const newAddBlocks = new Uint8Array(Math.ceil(blocks.length / 2));
  const changedPairs = new Map();
  const unmappedCounts = new Map();
  let changed = 0;

  for (let index = 0; index < blocks.length; index += 1) {
    const oldId = getBlockId(blocks, addBlocks, index);
    let newId = oldId;
    if (conversionMap.has(oldId)) {
      newId = conversionMap.get(oldId);
    } else if (knownIds.has(oldId)) {
      unmappedCounts.set(oldId, (unmappedCounts.get(oldId) ?? 0) + 1);
      if (unmappedMode === "air") {
        newId = 0;
        data[index] = 0;
      } else if (unmappedMode === "error") {
        throw new Error(`Bloc source connu sans correspondance: ID ${oldId}:0.`);
      }
    }

    if (newId !== oldId) {
      changed += 1;
      const key = `${oldId}->${newId}`;
      changedPairs.set(key, (changedPairs.get(key) ?? 0) + 1);
    }
    setBlockId(blocks, newAddBlocks, index, newId);
  }

  compoundSet(rootTag, "Blocks", { type: TAG_BYTE_ARRAY, value: blocks });
  compoundSet(rootTag, "Data", { type: TAG_BYTE_ARRAY, value: data });
  if (newAddBlocks.some((value) => value !== 0)) {
    compoundSet(rootTag, "AddBlocks", { type: TAG_BYTE_ARRAY, value: newAddBlocks });
  } else {
    compoundRemove(rootTag, "AddBlocks");
  }

  return {
    totalBlocks: blocks.length,
    changedBlocks: changed,
    changedPairs: [...changedPairs.entries()].map(([key, count]) => {
      const [from, to] = key.split("->").map(Number);
      return { from, to, count };
    }),
    unmappedKnown: [...unmappedCounts.entries()].map(([id, count]) => ({ id, count })),
  };
}

function outputName(inputName, targetPack) {
  const dot = inputName.lastIndexOf(".");
  const stem = dot >= 0 ? inputName.slice(0, dot) : inputName;
  const ext = dot >= 0 ? inputName.slice(dot) : ".schematic";
  return `${stem}.converted-${targetPack}${ext}`;
}

function downloadFile(filename, bytes, type = "application/octet-stream") {
  const blob = bytes instanceof Blob ? bytes : new Blob([bytes], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function renderReport(report) {
  lastReport = report;
  els.resultsSection.hidden = false;
  els.changedCount.textContent = String(report.changedBlocks);
  els.reportSummary.textContent = `${report.sourcePack} -> ${report.targetPack}, ${report.changedBlocks} blocs modifiés sur ${report.totalBlocks}.`;
  els.reportDetails.innerHTML = [
    ["Blocs total", report.totalBlocks],
    ["Blocs modifiés", report.changedBlocks],
    ["Mapping", report.mappingEntries],
    ["Sans correspondance", report.unmappedKnown.length],
  ]
    .map(([label, value]) => `<div class="report-item"><span>${label}</span><strong>${value}</strong></div>`)
    .join("");
}

async function handleConvert(event) {
  event.preventDefault();
  const file = els.file.files?.[0];
  if (!file) {
    setStatus("Choisis d'abord un fichier .schematic.", "warn");
    return;
  }

  try {
    els.convertButton.disabled = true;
    setStatus("Lecture du schematic...", "");
    const decoded = await decodeSchematic(file);
    const { name, tag } = parseRoot(decoded.buffer);
    const sourcePack = els.sourcePack.value;
    const targetPack = els.targetPack.value;
    const conversionMap = getConversionMap();
    const knownIds = getKnownSet(sourcePack);
    const stats = convertRoot(tag, conversionMap, knownIds, els.unmappedMode.value);

    const rawOutput = writeRoot(name, tag);
    const compression = els.compressionMode.value === "same" ? decoded.compression : els.compressionMode.value;
    setStatus("Écriture du fichier converti...", "");
    const outputBuffer = await encodeSchematic(rawOutput, compression);
    const filename = outputName(file.name, targetPack);
    downloadFile(filename, outputBuffer);

    const report = {
      input: file.name,
      output: filename,
      sourcePack,
      targetPack,
      inputCompression: decoded.compression,
      outputCompression: compression,
      mappingEntries: conversionMap.size,
      ...stats,
    };
    renderReport(report);
    setStatus(`Conversion terminée: ${stats.changedBlocks} blocs modifiés.`, "good");
  } catch (error) {
    setStatus(error.message, "bad");
  } finally {
    els.convertButton.disabled = false;
  }
}

els.file.addEventListener("change", () => {
  const file = els.file.files?.[0];
  els.fileName.textContent = file ? file.name : "Aucun fichier sélectionné";
});

els.sourcePack.addEventListener("change", updatePackControls);
els.targetPack.addEventListener("change", updatePackControls);
els.mappingSearch.addEventListener("input", renderMappingTable);

els.swapButton.addEventListener("click", () => {
  const source = els.sourcePack.value;
  els.sourcePack.value = els.targetPack.value;
  els.targetPack.value = source;
  updatePackControls();
});

els.saveReportButton.addEventListener("click", () => {
  if (!lastReport) return;
  const name = `${lastReport.output}.report.json`;
  downloadFile(name, new Blob([JSON.stringify(lastReport, null, 2)], { type: "application/json" }));
});

els.form.addEventListener("submit", handleConvert);
updatePackControls();
