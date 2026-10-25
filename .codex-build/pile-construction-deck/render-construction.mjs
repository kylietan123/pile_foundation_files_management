import fs from "node:fs/promises";
import path from "node:path";
import { FileBlob, PresentationFile } from "@oai/artifact-tool";
const finalPptx = "/Users/kylie/Desktop/桩基工程全过程管理/output/桩基施工管理专题汇报.pptx";
const out = "/Users/kylie/Desktop/桩基工程全过程管理/.codex-build/pile-construction-deck/construction-render";
await fs.mkdir(out, { recursive: true });
const presentation = await PresentationFile.importPptx(await FileBlob.load(finalPptx));
for (const [index, slide] of presentation.slides.items.entries()) {
  const png = await presentation.export({ slide, format: "png", scale: 1 });
  await fs.writeFile(path.join(out, `final-${String(index + 1).padStart(2, "0")}.png`), new Uint8Array(await png.arrayBuffer()));
}
console.log("RENDERED", presentation.slides.items.length);
