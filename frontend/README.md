# Suzent Frontend

The React-based user interface for Suzent.

## Requirements
- Node.js 18+
- npm 9+

## Development

1. **Install dependencies**:
   ```bash
   npm install
   ```

2. **Start development server**:
   ```bash
   npm run dev
   ```
   The app URL is printed by Vite in the terminal.
   
   > **Note**: This requires the backend API to be running.

## Building for Production

To create a static build for deployment:

```bash
npm run build
```
The output will be in the `dist/` directory.

## Configuration

The frontend connects to the backend API at `/api`. This is configured via Vite proxy in `vite.config.ts`.

