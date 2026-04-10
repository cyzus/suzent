function getHostPath(volume: string): string {
  const lastColon = volume.lastIndexOf(':');
  return lastColon === -1 ? volume : volume.substring(0, lastColon);
}

function getContainerPath(volume: string): string {
  const lastColon = volume.lastIndexOf(':');
  return lastColon === -1 ? '' : volume.substring(lastColon + 1);
}

function normalizeHostPath(path: string): string {
  return path.replace(/\\/g, '/').replace(/\/+$/, '');
}

export function buildMountedVolumes(currentVolumes: string[], paths: string[]): string[] {
  if (!paths || paths.length === 0) return currentVolumes;

  const nextVolumes = [...currentVolumes];

  paths.forEach((hostPath) => {
    const normalizedHost = normalizeHostPath(hostPath);
    if (!normalizedHost) return;

    const folderName = normalizedHost.split('/').pop() || 'data';
    let containerPath = `/mnt/${folderName}`;
    let counter = 1;

    while (nextVolumes.some(volume => getContainerPath(volume) === containerPath)) {
      containerPath = `/mnt/${folderName}-${counter}`;
      counter += 1;
    }

    const alreadyMounted = nextVolumes.some(volume => normalizeHostPath(getHostPath(volume)) === normalizedHost);
    if (!alreadyMounted) {
      nextVolumes.push(`${hostPath}:${containerPath}`);
    }
  });

  return nextVolumes;
}