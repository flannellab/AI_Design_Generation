import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const input = await FileBlob.load("ksz9563_lan7800_switch/ksz9563_lan7800_switch_BOM.xlsx");
const workbook = await SpreadsheetFile.importXlsx(input);
const preview = await workbook.inspect({
  kind: "table",
  range: "BOM!A1:L12",
  include: "values",
  tableMaxRows: 12,
  tableMaxCols: 12,
});
console.log(preview.ndjson);
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
});
console.log(errors.ndjson);
process.exitCode = 0;
