// electron-builder's NSIS template unpacks the app into a temp folder and then
// copies every file into the install folder, so each of the runtime's ~20k
// files is written (and scanned by Windows Defender) twice. Moving the
// unpacked folders instead is a rename on the same drive. The template has no
// hook for this step, so swap the copy for our macro (installer/installer.nsh).
import fs from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';

const require = createRequire(import.meta.url);
const templates = path.join(path.dirname(require.resolve('app-builder-lib/package.json')), 'templates', 'nsis');
const file = path.join(templates, 'include', 'extractAppPackage.nsh');
const copy = 'CopyFiles /SILENT "$PLUGINSDIR\\7z-out\\*" $OUTDIR';
const move = '!insertmacro suzentMoveExtracted';

const text = fs.readFileSync(file, 'utf8');
if (text.includes(move)) {
  console.log('NSIS template already moves the unpacked app');
} else if (text.split(copy).length === 2) {
  fs.writeFileSync(file, text.replace(copy, move));
  console.log(`Patched ${file}: move the unpacked app instead of copying it`);
} else {
  throw new Error(`${file} changed: expected exactly one "${copy}"`);
}
