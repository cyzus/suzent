import React, { useEffect, useRef } from 'react';
import type { VoiceSessionStatus } from '../../hooks/useVoiceSession';
import {
  buildVoxelShell,
  idlePose,
  stepVoxelShell,
  syllableEnvelope,
} from '../../lib/voice/voiceCubeSim';

const DEG = Math.PI / 180;
const CAM_Z = 410 / 82;
const VIEW_H = 2.02;

function mat4Perspective(fovRad: number, aspect: number, near: number, far: number): Float32Array {
  const f = 1 / Math.tan(fovRad / 2);
  const nf = 1 / (near - far);
  const m = new Float32Array(16);
  m[0] = f / aspect;
  m[5] = f;
  m[10] = (far + near) * nf;
  m[11] = -1;
  m[14] = 2 * far * near * nf;
  return m;
}

function mat4Mul(a: Float32Array, b: Float32Array): Float32Array {
  const out = new Float32Array(16);
  for (let c = 0; c < 4; c += 1) {
    for (let r = 0; r < 4; r += 1) {
      out[c * 4 + r] =
        a[0 * 4 + r] * b[c * 4 + 0] +
        a[1 * 4 + r] * b[c * 4 + 1] +
        a[2 * 4 + r] * b[c * 4 + 2] +
        a[3 * 4 + r] * b[c * 4 + 3];
    }
  }
  return out;
}

function mat4EulerXYZ(rx: number, ry: number, rz: number, ty = 0, tz = 0): Float32Array {
  const cx = Math.cos(rx);
  const sx = Math.sin(rx);
  const cy = Math.cos(ry);
  const sy = Math.sin(ry);
  const cz = Math.cos(rz);
  const sz = Math.sin(rz);
  const m = new Float32Array(16);
  m[0] = cy * cz;
  m[1] = sx * sy * cz + cx * sz;
  m[2] = -cx * sy * cz + sx * sz;
  m[4] = -cy * sz;
  m[5] = -sx * sy * sz + cx * cz;
  m[6] = cx * sy * sz + sx * cz;
  m[8] = sy;
  m[9] = -sx * cy;
  m[10] = cx * cy;
  m[12] = 0;
  m[13] = ty;
  m[14] = tz;
  m[15] = 1;
  return m;
}

const VOX_VS = `#version 300 es
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aNorm;
layout(location = 2) in vec3 iPos;
layout(location = 3) in vec3 iScale;
layout(location = 4) in float iBoost;
uniform mat4 uMVP;
uniform float uDark;
out float vLum;
void main() {
  vec3 bodyPos = iPos + aPos * iScale;
  gl_Position = uMVP * vec4(bodyPos, 1.0);
  vec3 u = clamp(bodyPos + 0.5, 0.0, 1.0);
  float base = 0.04;
  if (aNorm.y > 0.5) {
    base = 0.28 + 0.20 * u.z + 0.12 * u.x;
  } else if (aNorm.z > 0.5) {
    base = 0.13 + 0.16 * u.y + 0.07 * u.x;
  } else if (aNorm.x < -0.5) {
    base = 0.03 + 0.07 * u.y + 0.04 * u.z;
  }
  if (uDark > 0.5) base *= 0.86;
  vLum = clamp(base + iBoost, 0.0, 0.94);
}`;

const VOX_FS = `#version 300 es
precision highp float;
in float vLum;
out vec4 outColor;
void main() {
  outColor = vec4(vLum, vLum, vLum, 1.0);
}`;

const POST_VS = `#version 300 es
layout(location = 0) in vec2 aQuad;
out vec2 vUv;
void main() {
  vUv = aQuad * 0.5 + 0.5;
  gl_Position = vec4(aQuad, 0.0, 1.0);
}`;

const POST_FS = `#version 300 es
precision highp float;
uniform sampler2D uTex;
uniform vec2 uRes;
uniform float uPs;
uniform float uDark;
uniform float uShadowScale;
uniform float uShadowAlpha;
in vec2 vUv;
out vec4 outColor;

float bayer2(vec2 a){ a = floor(a); return fract(dot(a, vec2(0.5, a.y * 0.75))); }
float bayer4(vec2 a){ return bayer2(0.5 * a) * 0.25 + bayer2(a); }
float bayer8(vec2 a){ return bayer4(0.5 * a) * 0.25 + bayer2(a); }
float q(float v, float th){ float n = 6.0; return clamp(floor(v * n + th) / n, 0.0, 1.0); }

void main() {
  vec2 cell = floor(gl_FragCoord.xy / uPs);
  vec2 uv = (cell * uPs + 0.5 * uPs) / uRes;
  vec4 s = texture(uTex, uv);
  float th = bayer8(cell) + 0.5 / 64.0;
  vec3 ink = vec3(0.0);
  vec3 paper = vec3(1.0);
  vec3 shade = uDark > 0.5 ? vec3(0.95) : vec3(0.0);
  if (s.a > 0.9) {
    float l = s.r;
    if (l > 0.95) { outColor = vec4(paper, 1.0); return; }
    outColor = vec4(mix(ink, paper, q(l, th)), 1.0);
    return;
  }
  vec2 aspect = vec2(uRes.x / max(1.0, uRes.y), 1.0);
  vec2 d = (uv - vec2(0.5, 0.12)) * aspect / vec2(0.22 * uShadowScale, 0.032);
  float r2 = dot(d, d);
  if (r2 < 1.0) {
    float sh = exp(-r2 * 2.2) * uShadowAlpha;
    float qsh = q(sh * 1.2, th) * 0.85;
    if (qsh > 0.02) { outColor = vec4(shade, qsh); return; }
  }
  outColor = vec4(0.0);
}`;

function compileProgram(
  gl: WebGL2RenderingContext,
  vsSrc: string,
  fsSrc: string
): WebGLProgram | null {
  const compile = (type: number, src: string) => {
    const sh = gl.createShader(type);
    if (!sh) return null;
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      gl.deleteShader(sh);
      return null;
    }
    return sh;
  };
  const vs = compile(gl.VERTEX_SHADER, vsSrc);
  const fs = compile(gl.FRAGMENT_SHADER, fsSrc);
  if (!vs || !fs) return null;
  const prog = gl.createProgram();
  if (!prog) return null;
  gl.attachShader(prog, vs);
  gl.attachShader(prog, fs);
  gl.linkProgram(prog);
  gl.deleteShader(vs);
  gl.deleteShader(fs);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
    gl.deleteProgram(prog);
    return null;
  }
  return prog;
}

interface VoiceCubeStageProps {
  status: VoiceSessionStatus;
  working: boolean;
  micLevel?: { readonly current: number };
}

export const VoiceCubeStage: React.FC<VoiceCubeStageProps> = ({ status, working, micLevel }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef = useRef({ status, working, micLevel });
  stateRef.current = { status, working, micLevel };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let gl: WebGL2RenderingContext | null = null;
    try {
      gl = canvas.getContext('webgl2', { alpha: true, antialias: false });
    } catch {
      return;
    }
    if (!gl) return;

    const voxProg = compileProgram(gl, VOX_VS, VOX_FS);
    const postProg = compileProgram(gl, POST_VS, POST_FS);
    if (!voxProg || !postProg) return;

    // Interleaved pos (3) + normal (3) for 24 cube vertices
    const cubeVerts = new Float32Array([
      // +Z face
      -0.5, -0.5, 0.5, 0, 0, 1, 0.5, -0.5, 0.5, 0, 0, 1, 0.5, 0.5, 0.5, 0, 0, 1, -0.5, 0.5, 0.5, 0,
      0, 1,
      // -Z face
      -0.5, -0.5, -0.5, 0, 0, -1, -0.5, 0.5, -0.5, 0, 0, -1, 0.5, 0.5, -0.5, 0, 0, -1, 0.5, -0.5,
      -0.5, 0, 0, -1,
      // +Y face
      -0.5, 0.5, -0.5, 0, 1, 0, -0.5, 0.5, 0.5, 0, 1, 0, 0.5, 0.5, 0.5, 0, 1, 0, 0.5, 0.5, -0.5, 0,
      1, 0,
      // -Y face
      -0.5, -0.5, -0.5, 0, -1, 0, 0.5, -0.5, -0.5, 0, -1, 0, 0.5, -0.5, 0.5, 0, -1, 0, -0.5, -0.5,
      0.5, 0, -1, 0,
      // +X face
      0.5, -0.5, -0.5, 1, 0, 0, 0.5, 0.5, -0.5, 1, 0, 0, 0.5, 0.5, 0.5, 1, 0, 0, 0.5, -0.5, 0.5, 1,
      0, 0,
      // -X face
      -0.5, -0.5, -0.5, -1, 0, 0, -0.5, -0.5, 0.5, -1, 0, 0, -0.5, 0.5, 0.5, -1, 0, 0, -0.5, 0.5,
      -0.5, -1, 0, 0,
    ]);
    const cubeIdx = new Uint16Array([
      0, 1, 2, 0, 2, 3, 4, 5, 6, 4, 6, 7, 8, 9, 10, 8, 10, 11, 12, 13, 14, 12, 14, 15, 16, 17, 18,
      16, 18, 19, 20, 21, 22, 20, 22, 23,
    ]);

    const vox = buildVoxelShell();
    const totalInstances = 1 + vox.length;
    const instData = new Float32Array(totalInstances * 7);
    instData[0] = 0;
    instData[1] = 0;
    instData[2] = 0;
    instData[3] = 0.96;
    instData[4] = 0.96;
    instData[5] = 0.96;
    instData[6] = 0.0;

    const voxVao = gl.createVertexArray();
    gl.bindVertexArray(voxVao);

    const vbo = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
    gl.bufferData(gl.ARRAY_BUFFER, cubeVerts, gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 6 * 4, 0);
    gl.enableVertexAttribArray(1);
    gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 6 * 4, 3 * 4);

    const ebo = gl.createBuffer();
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, ebo);
    gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, cubeIdx, gl.STATIC_DRAW);

    const instBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, instBuf);
    gl.bufferData(gl.ARRAY_BUFFER, instData.byteLength, gl.DYNAMIC_DRAW);
    const stride = 7 * 4;
    gl.enableVertexAttribArray(2);
    gl.vertexAttribPointer(2, 3, gl.FLOAT, false, stride, 0);
    gl.vertexAttribDivisor(2, 1);
    gl.enableVertexAttribArray(3);
    gl.vertexAttribPointer(3, 3, gl.FLOAT, false, stride, 3 * 4);
    gl.vertexAttribDivisor(3, 1);
    gl.enableVertexAttribArray(4);
    gl.vertexAttribPointer(4, 1, gl.FLOAT, false, stride, 6 * 4);
    gl.vertexAttribDivisor(4, 1);

    const quadVao = gl.createVertexArray();
    gl.bindVertexArray(quadVao);
    const quadBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, quadBuf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.bindVertexArray(null);

    const fbo = gl.createFramebuffer();
    const rtTex = gl.createTexture();
    const depthRb = gl.createRenderbuffer();
    let rtW = 0;
    let rtH = 0;

    const ensureTarget = (w: number, h: number) => {
      if (w === rtW && h === rtH) return;
      rtW = Math.max(2, w);
      rtH = Math.max(2, h);
      canvas.width = rtW;
      canvas.height = rtH;
      gl!.bindTexture(gl!.TEXTURE_2D, rtTex);
      gl!.texImage2D(gl!.TEXTURE_2D, 0, gl!.RGBA8, rtW, rtH, 0, gl!.RGBA, gl!.UNSIGNED_BYTE, null);
      gl!.texParameteri(gl!.TEXTURE_2D, gl!.TEXTURE_MIN_FILTER, gl!.NEAREST);
      gl!.texParameteri(gl!.TEXTURE_2D, gl!.TEXTURE_MAG_FILTER, gl!.NEAREST);
      gl!.texParameteri(gl!.TEXTURE_2D, gl!.TEXTURE_WRAP_S, gl!.CLAMP_TO_EDGE);
      gl!.texParameteri(gl!.TEXTURE_2D, gl!.TEXTURE_WRAP_T, gl!.CLAMP_TO_EDGE);
      gl!.bindRenderbuffer(gl!.RENDERBUFFER, depthRb);
      gl!.renderbufferStorage(gl!.RENDERBUFFER, gl!.DEPTH_COMPONENT16, rtW, rtH);
      gl!.bindFramebuffer(gl!.FRAMEBUFFER, fbo);
      gl!.framebufferTexture2D(gl!.FRAMEBUFFER, gl!.COLOR_ATTACHMENT0, gl!.TEXTURE_2D, rtTex, 0);
      gl!.framebufferRenderbuffer(gl!.FRAMEBUFFER, gl!.DEPTH_ATTACHMENT, gl!.RENDERBUFFER, depthRb);
      gl!.bindFramebuffer(gl!.FRAMEBUFFER, null);
    };

    const uMVP = gl.getUniformLocation(voxProg, 'uMVP');
    const uVoxDark = gl.getUniformLocation(voxProg, 'uDark');
    const uTex = gl.getUniformLocation(postProg, 'uTex');
    const uRes = gl.getUniformLocation(postProg, 'uRes');
    const uPs = gl.getUniformLocation(postProg, 'uPs');
    const uDark = gl.getUniformLocation(postProg, 'uDark');
    const uShadowScale = gl.getUniformLocation(postProg, 'uShadowScale');
    const uShadowAlpha = gl.getUniformLocation(postProg, 'uShadowAlpha');

    const ptr = { x: 0, y: 0 };
    const ptrS = { x: 0, y: 0 };
    const onMove = (e: PointerEvent) => {
      if (e.pointerType !== 'mouse') return;
      const r = canvas.getBoundingClientRect();
      if (!r.width || !r.height) return;
      ptr.x = ((e.clientX - r.left) / r.width) * 2 - 1;
      ptr.y = ((e.clientY - r.top) / r.height) * 2 - 1;
    };
    const onLeave = () => {
      ptr.x = 0;
      ptr.y = 0;
    };
    canvas.addEventListener('pointermove', onMove);
    canvas.addEventListener('pointerleave', onLeave);

    const reduce =
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let raf = 0;
    let last = performance.now();
    let userSmooth = 0;
    let agentSmooth = 0;
    let lean = 0;

    const frame = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const t = reduce ? 0 : now / 1000;
      const { status: st, working: wrk, micLevel: mic } = stateRef.current;

      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const W = Math.max(2, Math.floor((rect.width || 220) * dpr));
      const H = Math.max(2, Math.floor((rect.height || 116) * dpr));
      ensureTarget(W, H);

      const rawMic = mic?.current ?? 0;
      const targetU =
        st === 'user_speaking' ? Math.max(rawMic, syllableEnvelope(t, 0.3) * 0.65) : rawMic * 0.6;
      const targetA = st === 'speaking' ? syllableEnvelope(t, 1.1) : 0;
      userSmooth += (targetU - userSmooth) * (targetU > userSmooth ? 0.5 : 0.18);
      agentSmooth += (targetA - agentSmooth) * (targetA > agentSmooth ? 0.45 : 0.16);

      const dark = document.documentElement.classList.contains('dark');
      stepVoxelShell(
        vox,
        {
          status: st,
          working: wrk,
          userLevel: userSmooth,
          agentLevel: agentSmooth,
          dark,
          t,
          dt: reduce ? 0 : dt,
        },
        instData,
        7
      );

      const fl = 0.5 - 0.5 * Math.cos((t * 2 * Math.PI) / 5.4);
      const floatY = (-2 + 7 * fl) / 82 + (st !== 'idle' ? 2 / 82 : 0);
      const [ix, iy, iz] = idlePose(t);
      ptrS.x += (ptr.x - ptrS.x) * Math.min(1, dt * 9);
      ptrS.y += (ptr.y - ptrS.y) * Math.min(1, dt * 9);
      lean += ((st === 'user_speaking' ? -3.5 : 0) - lean) * Math.min(1, dt * 4);
      const rx = -22 + ptrS.y * -7;
      const ry = 30 + ptrS.x * 12 + lean;

      const fov = 2 * Math.atan(VIEW_H / 2 / CAM_Z);
      const proj = mat4Perspective(fov, W / H, 0.1, 20);
      const viewFloatIdle = mat4EulerXYZ(-ix * DEG, iy * DEG, -iz * DEG, floatY, -CAM_Z);
      const pose = mat4EulerXYZ(-rx * DEG, ry * DEG, 0);
      const mvp = mat4Mul(proj, mat4Mul(viewFloatIdle, pose));

      gl!.bindFramebuffer(gl!.FRAMEBUFFER, fbo);
      gl!.viewport(0, 0, rtW, rtH);
      gl!.enable(gl!.DEPTH_TEST);
      gl!.clearColor(0, 0, 0, 0);
      gl!.clear(gl!.COLOR_BUFFER_BIT | gl!.DEPTH_BUFFER_BIT);
      gl!.useProgram(voxProg);
      gl!.uniformMatrix4fv(uMVP, false, mvp);
      gl!.uniform1f(uVoxDark, dark ? 1.0 : 0.0);
      gl!.bindVertexArray(voxVao);
      gl!.bindBuffer(gl!.ARRAY_BUFFER, instBuf);
      gl!.bufferSubData(gl!.ARRAY_BUFFER, 0, instData);
      gl!.drawElementsInstanced(gl!.TRIANGLES, 36, gl!.UNSIGNED_SHORT, 0, totalInstances);

      gl!.bindFramebuffer(gl!.FRAMEBUFFER, null);
      gl!.viewport(0, 0, rtW, rtH);
      gl!.disable(gl!.DEPTH_TEST);
      gl!.clearColor(0, 0, 0, 0);
      gl!.clear(gl!.COLOR_BUFFER_BIT);
      gl!.useProgram(postProg);
      gl!.activeTexture(gl!.TEXTURE0);
      gl!.bindTexture(gl!.TEXTURE_2D, rtTex);
      gl!.uniform1i(uTex, 0);
      gl!.uniform2f(uRes, rtW, rtH);
      gl!.uniform1f(uPs, 1.0);
      gl!.uniform1f(uDark, dark ? 1.0 : 0.0);
      gl!.uniform1f(uShadowScale, 1 - 0.22 * fl);
      gl!.uniform1f(uShadowAlpha, (st !== 'idle' ? 0.08 : 0.14 - 0.06 * fl) * 2.2);
      gl!.bindVertexArray(quadVao);
      gl!.drawArrays(gl!.TRIANGLE_STRIP, 0, 4);

      raf = requestAnimationFrame(frame);
    };

    raf = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(raf);
      canvas.removeEventListener('pointermove', onMove);
      canvas.removeEventListener('pointerleave', onLeave);
      gl?.deleteFramebuffer(fbo);
      gl?.deleteTexture(rtTex);
      gl?.deleteRenderbuffer(depthRb);
      gl?.deleteBuffer(vbo);
      gl?.deleteBuffer(ebo);
      gl?.deleteBuffer(instBuf);
      gl?.deleteBuffer(quadBuf);
      gl?.deleteVertexArray(voxVao);
      gl?.deleteVertexArray(quadVao);
      gl?.deleteProgram(voxProg);
      gl?.deleteProgram(postProg);
    };
  }, []);

  return (
    <div className="flex justify-center py-1">
      <canvas
        ref={canvasRef}
        aria-hidden="true"
        data-testid="voice-cube-stage"
        className="block h-28 w-full max-w-[260px]"
      />
    </div>
  );
};
