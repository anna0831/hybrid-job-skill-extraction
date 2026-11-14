/**
 * jieba_lite.js — Exact JavaScript port of Python jieba.cut (HMM=True, cut_all=False) + add_word.
 * Works 100% offline under file:// in Chrome and in Node.js for verification.
 */
(function (root) {
  "use strict";

  const MIN_FLOAT = -3.14e100;
  const PREV_STATUS = {
    B: ["E", "S"],
    M: ["M", "B"],
    S: ["S", "E"],
    E: ["B", "M"],
  };
  const RE_HAN_DEFAULT = /([\u4E00-\u9FD5a-zA-Z0-9+#&\._%-]+)/;
  const RE_SKIP_DEFAULT = /(\r\n|\s)/;
  const RE_HAN_FINALSEG = /([\u4E00-\u9FD5]+)/;
  const RE_SKIP_FINALSEG = /([a-zA-Z0-9]+(?:\.\d+)?%?)/;

  async function gunzipBase64ToText(b64) {
    const binStr = atob(b64);
    const bytes = new Uint8Array(binStr.length);
    for (let i = 0; i < binStr.length; i++) bytes[i] = binStr.charCodeAt(i);
    if (typeof DecompressionStream !== "undefined") {
      const ds = new DecompressionStream("gzip");
      const stream = new Blob([bytes]).stream().pipeThrough(ds);
      const ab = await new Response(stream).arrayBuffer();
      return new TextDecoder("utf-8").decode(ab);
    }
    throw new Error("目前瀏覽器不支援 DecompressionStream('gzip')，請使用新版 Chrome。");
  }

  function splitWithKeep(str, re) {
    const out = [];
    const globalRe = new RegExp(re.source, "g");
    let last = 0;
    let m;
    while ((m = globalRe.exec(str)) !== null) {
      if (m.index > last) out.push(str.slice(last, m.index));
      out.push(m[0]);
      last = m.index + m[0].length;
      if (m[0].length === 0) globalRe.lastIndex++;
    }
    if (last < str.length) out.push(str.slice(last));
    return out;
  }

  class JiebaLite {
    constructor() {
      this.FREQ = new Map();
      this.total = 0;
      this.probStart = null;
      this.probTrans = null;
      this.probEmit = null;
      this.initialized = false;
    }

    async initFromBase64(b64) {
      if (this.initialized) return;
      const jsonStr = await gunzipBase64ToText(b64);
      const data = JSON.parse(jsonStr);
      this.probStart = data.start;
      this.probTrans = data.trans;
      this.probEmit = data.emit;

      const lines = data.dict.split("\n");
      let total = 0;
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        if (!line) continue;
        const tab = line.indexOf("\t");
        if (tab <= 0) continue;
        const word = line.slice(0, tab);
        const freq = parseInt(line.slice(tab + 1), 10) || 0;
        this.FREQ.set(word, freq);
        total += freq;
        for (let ch = 0; ch < word.length; ch++) {
          const frag = word.slice(0, ch + 1);
          if (!this.FREQ.has(frag)) this.FREQ.set(frag, 0);
        }
      }
      this.total = total;
      this.initialized = true;
    }

    addWord(word, freq) {
      if (!word) return;
      const prev = this.FREQ.get(word) || 0;
      this.FREQ.set(word, freq);
      this.total += freq - prev;
      for (let ch = 0; ch < word.length; ch++) {
        const frag = word.slice(0, ch + 1);
        if (!this.FREQ.has(frag)) this.FREQ.set(frag, 0);
      }
    }

    getDAG(sentence) {
      const DAG = {};
      const N = sentence.length;
      for (let k = 0; k < N; k++) {
        const tmplist = [];
        let i = k;
        let frag = sentence[k];
        while (i < N && this.FREQ.has(frag)) {
          if (this.FREQ.get(frag) > 0) tmplist.push(i);
          i += 1;
          frag = sentence.slice(k, i + 1);
        }
        if (tmplist.length === 0) tmplist.push(k);
        DAG[k] = tmplist;
      }
      return DAG;
    }

    calc(sentence, DAG) {
      const N = sentence.length;
      const route = new Array(N + 1);
      route[N] = [0, 0];
      const logtotal = Math.log(this.total || 1);
      for (let idx = N - 1; idx >= 0; idx--) {
        let bestScore = -Infinity;
        let bestEnd = idx;
        const list = DAG[idx];
        for (let j = 0; j < list.length; j++) {
          const x = list[j];
          const w = sentence.slice(idx, x + 1);
          const f = this.FREQ.get(w) || 1;
          const score = Math.log(f) - logtotal + route[x + 1][0];
          if (score > bestScore) {
            bestScore = score;
            bestEnd = x;
          }
        }
        route[idx] = [bestScore, bestEnd];
      }
      return route;
    }

    viterbi(obs) {
      const V = [{}];
      let path = {};
      const states = ["B", "M", "E", "S"];
      for (let i = 0; i < states.length; i++) {
        const y = states[i];
        const emP = this.probEmit[y][obs[0]] !== undefined ? this.probEmit[y][obs[0]] : MIN_FLOAT;
        V[0][y] = this.probStart[y] + emP;
        path[y] = [y];
      }
      for (let t = 1; t < obs.length; t++) {
        V.push({});
        const newpath = {};
        for (let i = 0; i < states.length; i++) {
          const y = states[i];
          const emP = this.probEmit[y][obs[t]] !== undefined ? this.probEmit[y][obs[t]] : MIN_FLOAT;
          let bestProb = -Infinity;
          let bestState = PREV_STATUS[y][0];
          const prevs = PREV_STATUS[y];
          for (let j = 0; j < prevs.length; j++) {
            const y0 = prevs[j];
            const transP = this.probTrans[y0][y] !== undefined ? this.probTrans[y0][y] : MIN_FLOAT;
            const p = V[t - 1][y0] + transP + emP;
            if (p > bestProb || (p === bestProb && y0 > bestState)) {
              bestProb = p;
              bestState = y0;
            }
          }
          V[t][y] = bestProb;
          newpath[y] = path[bestState].concat(y);
        }
        path = newpath;
      }
      const endStates = ["E", "S"];
      let bestEndProb = -Infinity;
      let bestEndState = "E";
      for (let i = 0; i < endStates.length; i++) {
        const y = endStates[i];
        const p = V[obs.length - 1][y];
        if (p > bestEndProb || (p === bestEndProb && y > bestEndState)) {
          bestEndProb = p;
          bestEndState = y;
        }
      }
      return path[bestEndState];
    }

    cutHMM(sentence) {
      const posList = this.viterbi(sentence);
      const out = [];
      let begin = 0;
      let nexti = 0;
      for (let i = 0; i < sentence.length; i++) {
        const pos = posList[i];
        if (pos === "B") {
          begin = i;
        } else if (pos === "E") {
          out.push(sentence.slice(begin, i + 1));
          nexti = i + 1;
        } else if (pos === "S") {
          out.push(sentence[i]);
          nexti = i + 1;
        }
      }
      if (nexti < sentence.length) out.push(sentence.slice(nexti));
      return out;
    }

    finalsegCut(sentence) {
      const blocks = splitWithKeep(sentence, RE_HAN_FINALSEG);
      const out = [];
      for (let i = 0; i < blocks.length; i++) {
        const blk = blocks[i];
        if (!blk) continue;
        if (RE_HAN_FINALSEG.test(blk)) {
          const segs = this.cutHMM(blk);
          for (let j = 0; j < segs.length; j++) out.push(segs[j]);
        } else {
          const tmp = splitWithKeep(blk, RE_SKIP_FINALSEG);
          for (let j = 0; j < tmp.length; j++) {
            if (tmp[j]) out.push(tmp[j]);
          }
        }
      }
      return out;
    }

    cutDAG(sentence) {
      const DAG = this.getDAG(sentence);
      const route = this.calc(sentence, DAG);
      const N = sentence.length;
      const out = [];
      let x = 0;
      let buf = "";
      while (x < N) {
        const y = route[x][1] + 1;
        const lWord = sentence.slice(x, y);
        if (y - x === 1) {
          buf += lWord;
        } else {
          if (buf) {
            if (buf.length === 1) {
              out.push(buf);
              buf = "";
            } else {
              if (!this.FREQ.has(buf) || this.FREQ.get(buf) === 0) {
                const recognized = this.finalsegCut(buf);
                for (let j = 0; j < recognized.length; j++) out.push(recognized[j]);
              } else {
                for (let j = 0; j < buf.length; j++) out.push(buf[j]);
              }
              buf = "";
            }
          }
          out.push(lWord);
        }
        x = y;
      }
      if (buf) {
        if (buf.length === 1) {
          out.push(buf);
        } else if (!this.FREQ.has(buf) || this.FREQ.get(buf) === 0) {
          const recognized = this.finalsegCut(buf);
          for (let j = 0; j < recognized.length; j++) out.push(recognized[j]);
        } else {
          for (let j = 0; j < buf.length; j++) out.push(buf[j]);
        }
      }
      return out;
    }

    cut(sentence) {
      if (!sentence) return [];
      const blocks = splitWithKeep(String(sentence), RE_HAN_DEFAULT);
      const out = [];
      for (let i = 0; i < blocks.length; i++) {
        const blk = blocks[i];
        if (!blk) continue;
        if (RE_HAN_DEFAULT.test(blk)) {
          const words = this.cutDAG(blk);
          for (let j = 0; j < words.length; j++) out.push(words[j]);
        } else {
          const tmp = splitWithKeep(blk, RE_SKIP_DEFAULT);
          for (let j = 0; j < tmp.length; j++) {
            const x = tmp[j];
            if (!x) continue;
            if (RE_SKIP_DEFAULT.test(x)) {
              out.push(x);
            } else {
              for (let k = 0; k < x.length; k++) out.push(x[k]);
            }
          }
        }
      }
      return out;
    }
  }

  root.JiebaLite = JiebaLite;
})(typeof window !== "undefined" ? window : globalThis);
