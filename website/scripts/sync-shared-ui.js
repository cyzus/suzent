const fs = require('fs');
const path = require('path');

const SOURCE_DIR = path.resolve(__dirname, '../../frontend/src');
const DEST_DIR = path.resolve(__dirname, '../src');

const FILES_TO_SYNC = [
    {
        src: 'components/chat/RobotAvatar.tsx',
        dest: 'components/RobotAvatar.tsx',
    },
    {
        src: 'robot-animations.css',
        dest: 'css/robot-animations.css',
    },
];

console.log('Syncing shared UI components from frontend...');

FILES_TO_SYNC.forEach(({ src, dest }) => {
    const srcPath = path.join(SOURCE_DIR, src);
    const destPath = path.join(DEST_DIR, dest);

    if (fs.existsSync(srcPath)) {
        const content = fs.readFileSync(srcPath, 'utf8');
        // Ensure destination dir exists
        const destDir = path.dirname(destPath);
        if (!fs.existsSync(destDir)) {
            fs.mkdirSync(destDir, { recursive: true });
        }
        fs.writeFileSync(destPath, content);
        console.log(`Copied ${src} -> ${dest}`);
    } else {
        console.error(`Error: Source file not found: ${srcPath}`);
        process.exit(1);
    }
});

console.log('Sync complete.');
