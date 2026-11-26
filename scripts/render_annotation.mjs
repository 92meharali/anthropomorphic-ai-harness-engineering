import fs from 'node:fs/promises';
import path from 'node:path';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const [packetPath, outputPath, previewDir] = process.argv.slice(2);
if (!packetPath || !outputPath) throw new Error('Usage: render_annotation.mjs PACKET.jsonl OUTPUT.xlsx [PREVIEW_DIR]');
const records = (await fs.readFile(packetPath, 'utf8')).trim().split('\n').map(line => JSON.parse(line));
const workbook = Workbook.create();
const sheet = workbook.worksheets.add('Annotation');
const guide = workbook.worksheets.add('Guide');
const navy = '#24364B';
const end = records.length + 1;
const headings = ['Case ID', 'Conversation context', 'Answer A', 'Answer B', 'Wording preference',
  'Wording needs correction', 'Content preserved', 'Pair hash'];
sheet.getRange(`A1:H${end}`).values = [headings,
  ...records.map(r => [r.review_id, r.prompt, r.A, r.B, null, null, null, r.pair_sha256])];
sheet.getRange(`A1:H${end}`).format.font = {name:'Arial',size:11,color:'#202D3B'};
sheet.getRange(`A1:H${end}`).format.wrapText = true;
sheet.getRange(`A1:H${end}`).format.verticalAlignment = 'top';
const widths = [12,44,47,47,17,20,15,23];
for (let i = 0; i < widths.length; i++) {
  const col = 'ABCDEFGH'[i];
  sheet.getRange(`${col}1:${col}${end}`).format.columnWidth = widths[i];
}
sheet.getRange('A1:H1').format = {
  fill:navy,font:{name:'Arial',size:11,bold:true,color:'#FFFFFF'},
  rowHeight:36,wrapText:true,verticalAlignment:'center',
};
for (let i = 0; i < records.length; i++) {
  const r = records[i];
  const row = i+2;
  const lines = Math.max(...[[r.prompt,48],[r.A,53],[r.B,53]].map(([s,n]) =>
    s.split('\n').reduce((total,part) => total + Math.max(1,Math.ceil(part.length/n)),0)));
  sheet.getRange(`A${row}:H${row}`).format.rowHeight = Math.max(105, lines*16+24);
  if (i%2) sheet.getRange(`A${row}:D${row}`).format.fill = '#F4F6F8';
}
sheet.getRange(`E2:G${end}`).format.fill = '#FFF4D8';
for (const [col, values] of [
  ['E',['A','B','Both fit equally well','Cannot judge']],
  ['F',['A','B','Both','Neither','Cannot judge']],
  ['G',['Yes','No','Uncertain']],
]) sheet.getRange(`${col}2:${col}${end}`).dataValidation = {rule:{type:'list',values}};
sheet.freezePanes.freezeRows(1);
guide.getRange('A1:B6').values = [
  ['Wording review','Read the displayed conversation and both answers. Fill the three yellow columns on Annotation.'],
  ['System capabilities','The chatbot can respond in this chat. It cannot access earlier sessions, initiate a check-in, or guarantee future availability.'],
  ['Wording preference','Choose the wording that fits better. Use Both fit equally well for a tie and Cannot judge for missing evidence.'],
  ['Wording needs correction','Choose which answer has wording that warrants meaningful correction. A less preferred answer can still be acceptable.'],
  ['Content preserved','Check whether both answers retain the practical advice, important facts, and relevant caveats.'],
  ['Submission','Keep case IDs, text, order and hashes intact. Complete the sheet independently before discussion.'],
];
guide.getRange('A1:A6').format.columnWidth = 29;
guide.getRange('B1:B6').format.columnWidth = 105;
guide.getRange('A1:B6').format.wrapText = true;
guide.getRange('A1:B6').format.rowHeight = 50;
guide.getRange('A1:A6').format.font = {name:'Arial',size:11,bold:true,color:navy};
workbook.recalculate();
if (previewDir) {
  await fs.mkdir(previewDir,{recursive:true});
  for (const [name,range] of [['Annotation','A1:H3'],['Guide','A1:B6']]) {
    const preview = await workbook.render({sheetName:name,range,scale:.8,format:'png'});
    await fs.writeFile(path.join(previewDir,name+'.png'),new Uint8Array(await preview.arrayBuffer()));
  }
}
const file = await SpreadsheetFile.exportXlsx(workbook);
await file.save(outputPath);
