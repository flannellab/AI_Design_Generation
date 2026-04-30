import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const projectDir = path.resolve("ksz9563_lan7800_switch");
const csvPath = path.join(projectDir, "ksz9563_lan7800_switch_BOM.csv");
const xlsxPath = path.join(projectDir, "ksz9563_lan7800_switch_BOM.xlsx");

const csvText = await fs.readFile(csvPath, "utf8");
const workbook = await Workbook.fromCSV(csvText, { sheetName: "BOM" });

const preview = await workbook.inspect({
  kind: "table",
  range: "BOM!A1:L20",
  include: "values",
  tableMaxRows: 20,
  tableMaxCols: 12,
});
console.log(preview.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(xlsxPath);
console.log(xlsxPath);
process.exitCode = 0;
