<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import * as THREE from 'three'

// 单相机映射三参数：水平角(0-360) / 垂直角(-30~60) / 缩放(0-10)
// 与 ComfyUI QwenMultiangleCameraNode 的 prompt 生成逻辑保持一致
const props = defineProps<{
  initialH?: number
  initialV?: number
  initialZ?: number
  imageUrl?: string | null
}>()

const emit = defineEmits<{
  'update:angle': [h: number, v: number, z: number]
}>()

const azimuth = ref(props.initialH ?? 0)
const elevation = ref(props.initialV ?? 0)
const distance = ref(props.initialZ ?? 5)
const promptText = ref('')
const wrapRef = ref<HTMLElement | null>(null)

// ── 观察相机轨道（第三人称视角，右键拖动旋转；不影响被调相机/手柄）──
let orbitAz = Math.atan2(4, 4) * 180 / Math.PI   // 默认相机方位 ≈45°
let orbitEl = 35                                  // 默认俯仰 ≈35°
let orbitDist = 6.5                               // 默认观察距离
let orbitDragging = false
let orbitLastX = 0
let orbitLastY = 0

// ── three.js 场景 ──
let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let cameraIndicator: THREE.Mesh | null = null
let camGlow: THREE.Mesh | null = null
let imagePlane: THREE.Mesh | null = null
let imageFrame: THREE.LineSegments | null = null
let planeMat: THREE.MeshBasicMaterial | null = null
let distanceLine: THREE.Line | null = null
let azimuthRing: THREE.Mesh | null = null
let elevationArc: THREE.Mesh | null = null
let gridHelper: THREE.GridHelper | null = null
let glowRing: THREE.Mesh | null = null
// 三球手柄（仿 ComfyUI：粉=水平 / 青=垂直 / 黄=距离）
let azimuthHandle: THREE.Mesh | null = null
let azGlow: THREE.Mesh | null = null
let elevationHandle: THREE.Mesh | null = null
let elGlow: THREE.Mesh | null = null
let distanceHandle: THREE.Mesh | null = null
let distGlow: THREE.Mesh | null = null
let raycaster = new THREE.Raycaster()
let mouse = new THREE.Vector2()
let isDragging = false
let dragTarget: string | null = null  // 'azimuth' | 'elevation' | 'distance'
let hoveredHandle: string | null = null
let animationId: number | null = null
let time = 0
const CENTER = new THREE.Vector3(0, 0.5, 0)
const AZIMUTH_RADIUS = 1.8
const ELEVATION_RADIUS = 1.4
const ELEV_ARC_X = -0.8

function generatePrompt(): string {
  const hAngle = ((azimuth.value % 360) + 360) % 360
  let hDirection: string
  if (hAngle < 22.5 || hAngle >= 337.5) hDirection = 'front view'
  else if (hAngle < 67.5) hDirection = 'front-right quarter view'
  else if (hAngle < 112.5) hDirection = 'right side view'
  else if (hAngle < 157.5) hDirection = 'back-right quarter view'
  else if (hAngle < 202.5) hDirection = 'back view'
  else if (hAngle < 247.5) hDirection = 'back-left quarter view'
  else if (hAngle < 292.5) hDirection = 'left side view'
  else hDirection = 'front-left quarter view'

  let vDirection: string
  if (elevation.value < -15) vDirection = 'low-angle shot'
  else if (elevation.value < 15) vDirection = 'eye-level shot'
  else if (elevation.value < 45) vDirection = 'elevated shot'
  else vDirection = 'high-angle shot'

  let dist: string
  if (distance.value < 2) dist = 'wide shot'
  else if (distance.value < 6) dist = 'medium shot'
  else dist = 'close-up'

  return `<sks> ${hDirection} ${vDirection} ${dist}`
}

function updateVisuals() {
  if (!scene || !cameraIndicator || !camGlow) return
  const azRad = (azimuth.value * Math.PI) / 180
  const elRad = (elevation.value * Math.PI) / 180
  const visualDist = 2.6 - (distance.value / 10) * 2.0

  const camX = visualDist * Math.sin(azRad) * Math.cos(elRad)
  const camY = CENTER.y + visualDist * Math.sin(elRad)
  const camZ = visualDist * Math.cos(azRad) * Math.cos(elRad)

  cameraIndicator.position.set(camX, camY, camZ)
  cameraIndicator.lookAt(CENTER)
  cameraIndicator.rotateX(Math.PI / 2)
  camGlow.position.copy(cameraIndicator.position)

  // 三球手柄位置
  const azX = AZIMUTH_RADIUS * Math.sin(azRad)
  const azZ = AZIMUTH_RADIUS * Math.cos(azRad)
  if (azimuthHandle) { azimuthHandle.position.set(azX, 0.16, azZ); if (azGlow) azGlow.position.copy(azimuthHandle.position) }
  const elY = CENTER.y + ELEVATION_RADIUS * Math.sin(elRad)
  const elZ = ELEVATION_RADIUS * Math.cos(elRad)
  if (elevationHandle) { elevationHandle.position.set(ELEV_ARC_X, elY, elZ); if (elGlow) elGlow.position.copy(elevationHandle.position) }
  const distT = 0.15 + ((10 - distance.value) / 10) * 0.7
  if (distanceHandle) {
    distanceHandle.position.lerpVectors(CENTER, cameraIndicator.position, distT)
    if (distGlow) distGlow.position.copy(distanceHandle.position)
  }

  // 相机连线：复用 Line 原地更新顶点，避免每帧重建几何体（性能关键）
  if (!distanceLine) {
    const lineGeo = new THREE.BufferGeometry()
    lineGeo.setAttribute('position', new THREE.Float32BufferAttribute([0, 0, 0, 0, 0, 0], 3))
    const lineMat = new THREE.LineBasicMaterial({ color: 0xFFB800, transparent: true, opacity: 0.8 })
    distanceLine = new THREE.Line(lineGeo, lineMat)
    scene.add(distanceLine)
  }
  const pos = (distanceLine.geometry.getAttribute('position') as THREE.BufferAttribute)
  pos.setXYZ(0, CENTER.x, CENTER.y, CENTER.z)
  pos.setXYZ(1, camX, camY, camZ)
  pos.needsUpdate = true
}

function notify() {
  emit('update:angle', Math.round(azimuth.value), Math.round(elevation.value), Math.round(distance.value * 10) / 10)
}

function initThree() {
  const container = wrapRef.value
  if (!container) return
  const width = container.clientWidth || 340
  const height = container.clientHeight || 300

  scene = new THREE.Scene()
  scene.background = new THREE.Color(0x0a0a0f)

  camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 1000)
  camera.position.set(4, 3.5, 4)
  camera.lookAt(0, 0.3, 0)

  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  renderer.setSize(width, height, false)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.outputColorSpace = THREE.SRGBColorSpace
  container.appendChild(renderer.domElement)
  const canvas = renderer.domElement
  canvas.style.position = 'absolute'
  canvas.style.top = '0'
  canvas.style.left = '0'
  canvas.style.width = '100%'
  canvas.style.height = '100%'

  scene.add(new THREE.AmbientLight(0xffffff, 0.4))
  const mainLight = new THREE.DirectionalLight(0xffffff, 0.8)
  mainLight.position.set(5, 10, 5)
  scene.add(mainLight)
  const fillLight = new THREE.DirectionalLight(0xE93D82, 0.3)
  fillLight.position.set(-5, 5, -5)
  scene.add(fillLight)

  gridHelper = new THREE.GridHelper(5, 20, 0x1a1a2e, 0x12121a)
  gridHelper.position.y = -0.01
  scene.add(gridHelper)

  // 中央图片卡片
  const cardGeo = new THREE.BoxGeometry(1.2, 1.2, 0.02)
  planeMat = new THREE.MeshBasicMaterial({ color: 0x3a3a4a })
  const backMat = new THREE.MeshBasicMaterial({ color: 0x1a1a2a })
  const edgeMat = new THREE.MeshBasicMaterial({ color: 0x1a1a2a })
  imagePlane = new THREE.Mesh(cardGeo, [edgeMat, edgeMat, edgeMat, edgeMat, planeMat, backMat])
  imagePlane.position.copy(CENTER)
  scene.add(imagePlane)

  const frameGeo = new THREE.EdgesGeometry(cardGeo)
  const frameMat = new THREE.LineBasicMaterial({ color: 0xE93D82 })
  imageFrame = new THREE.LineSegments(frameGeo, frameMat)
  imageFrame.position.copy(CENTER)
  scene.add(imageFrame)

  const glowRingGeo = new THREE.RingGeometry(0.55, 0.58, 64)
  const glowRingMat = new THREE.MeshBasicMaterial({ color: 0xE93D82, transparent: true, opacity: 0.4, side: THREE.DoubleSide })
  glowRing = new THREE.Mesh(glowRingGeo, glowRingMat)
  glowRing.position.set(0, 0.01, 0)
  glowRing.rotation.x = -Math.PI / 2
  scene.add(glowRing)

  // 相机指示器（单相机 = 三参数映射）
  const camGeo = new THREE.ConeGeometry(0.15, 0.4, 4)
  const camMat = new THREE.MeshStandardMaterial({ color: 0xE93D82, emissive: 0xE93D82, emissiveIntensity: 0.5, metalness: 0.8, roughness: 0.2 })
  cameraIndicator = new THREE.Mesh(camGeo, camMat)
  scene.add(cameraIndicator)
  const camGlowGeo = new THREE.SphereGeometry(0.08, 16, 16)
  const camGlowMat = new THREE.MeshBasicMaterial({ color: 0xff6ba8, transparent: true, opacity: 0.8 })
  camGlow = new THREE.Mesh(camGlowGeo, camGlowMat)
  scene.add(camGlow)

  // 三球手柄（仿 ComfyUI）：粉=水平 / 青=垂直 / 黄=距离
  const _scene = scene  // initThree 内已赋值非空
  const mkHandle = (color: number, glowColor: number) => {
    const geo = new THREE.SphereGeometry(0.16, 32, 32)
    const mat = new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0.6, metalness: 0.3, roughness: 0.4 })
    const mesh = new THREE.Mesh(geo, mat)
    _scene!.add(mesh)
    const glowGeo = new THREE.SphereGeometry(0.22, 16, 16)
    const glowMat = new THREE.MeshBasicMaterial({ color: glowColor, transparent: true, opacity: 0.2 })
    const glow = new THREE.Mesh(glowGeo, glowMat)
    _scene!.add(glow)
    return { mesh, glow }
  }
  const azH = mkHandle(0xE93D82, 0xE93D82)
  azimuthHandle = azH.mesh; azGlow = azH.glow
  const elH = mkHandle(0x00FFD0, 0x00FFD0)
  elevationHandle = elH.mesh; elGlow = elH.glow
  const distH = mkHandle(0xFFB800, 0xFFB800)
  distanceHandle = distH.mesh; distGlow = distH.glow

  // 水平圆环 + 垂直弧线（视觉辅助，可拖拽目标简化：拖相机即可）
  const azRingGeo = new THREE.TorusGeometry(AZIMUTH_RADIUS, 0.02, 16, 100)
  const azRingMat = new THREE.MeshBasicMaterial({ color: 0xE93D82, transparent: true, opacity: 0.4 })
  azimuthRing = new THREE.Mesh(azRingGeo, azRingMat)
  azimuthRing.rotation.x = Math.PI / 2
  azimuthRing.position.y = 0.02
  scene.add(azimuthRing)

  const arcPoints: THREE.Vector3[] = []
  for (let i = 0; i <= 32; i++) {
    const angle = (-30 + (90 * i / 32)) * Math.PI / 180
    arcPoints.push(new THREE.Vector3(ELEV_ARC_X, ELEVATION_RADIUS * Math.sin(angle) + CENTER.y, ELEVATION_RADIUS * Math.cos(angle)))
  }
  const arcCurve = new THREE.CatmullRomCurve3(arcPoints)
  const elArcGeo = new THREE.TubeGeometry(arcCurve, 32, 0.02, 8, false)
  const elArcMat = new THREE.MeshBasicMaterial({ color: 0x00FFD0, transparent: true, opacity: 0.5 })
  elevationArc = new THREE.Mesh(elArcGeo, elArcMat)
  scene.add(elevationArc)

  updateVisuals()

  // 事件
  canvas.addEventListener('mousedown', onPointerDown)
  window.addEventListener('mousemove', onPointerMove)
  window.addEventListener('mouseup', onPointerUp)
  canvas.addEventListener('contextmenu', onContextMenu)
  canvas.addEventListener('touchstart', onTouchStart, { passive: false })
  canvas.addEventListener('touchmove', onTouchMove, { passive: false })
  canvas.addEventListener('touchend', onPointerUp)

  const resizeObs = new ResizeObserver(() => {
    if (renderer && camera && container) {
      const w = container.clientWidth
      const h = container.clientHeight
      if (w > 0 && h > 0) {
        camera.aspect = w / h
        camera.updateProjectionMatrix()
        renderer.setSize(w, h, false)
      }
    }
  })
  resizeObs.observe(container)

  const loop = () => {
    animationId = requestAnimationFrame(loop)
    time += 0.01
    const pulse = 1 + Math.sin(time * 2) * 0.03
    if (camGlow) camGlow.scale.setScalar(pulse)
    if (glowRing) glowRing.rotation.z += 0.003
    if (renderer && scene && camera) {
      // 观察相机跟随轨道（右键拖动可旋转第三人称视角）
      const azRad = orbitAz * Math.PI / 180
      const elRad = orbitEl * Math.PI / 180
      camera.position.set(
        CENTER.x + orbitDist * Math.sin(azRad) * Math.cos(elRad),
        CENTER.y + orbitDist * Math.sin(elRad),
        CENTER.z + orbitDist * Math.cos(azRad) * Math.cos(elRad),
      )
      camera.lookAt(CENTER.x, CENTER.y, CENTER.z)
      renderer.render(scene, camera)
    }
  }
  loop()

  if (props.imageUrl) loadImage(props.imageUrl)
}

function getMouse(event: { clientX: number; clientY: number }) {
  if (!renderer) return
  const rect = renderer.domElement.getBoundingClientRect()
  mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
  mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1
}

function onContextMenu(e: Event) { e.preventDefault() }

function onPointerDown(event: MouseEvent) {
  if (!renderer || !camera) return
  // 右键：轨道旋转第三人称视角
  if (event.button === 2) {
    orbitDragging = true
    orbitLastX = event.clientX
    orbitLastY = event.clientY
    renderer.domElement.style.cursor = 'grabbing'
    event.preventDefault()
    return
  }
  getMouse(event)
  raycaster.setFromCamera(mouse, camera)
  const handles = [
    { mesh: azimuthHandle, glow: azGlow, name: 'azimuth' },
    { mesh: elevationHandle, glow: elGlow, name: 'elevation' },
    { mesh: distanceHandle, glow: distGlow, name: 'distance' },
  ]
  for (const h of handles) {
    if (h.mesh && raycaster.intersectObject(h.mesh).length > 0) {
      isDragging = true
      dragTarget = h.name
      h.mesh.scale.setScalar(1.3)
      renderer.domElement.style.cursor = 'grabbing'
      return
    }
  }
}

function onPointerMove(event: MouseEvent) {
  if (!renderer || !camera) return
  // 右键轨道旋转：绕场景中心水平+垂直转
  if (orbitDragging) {
    const dx = event.clientX - orbitLastX
    const dy = event.clientY - orbitLastY
    orbitLastX = event.clientX
    orbitLastY = event.clientY
    orbitAz = ((orbitAz - dx * 0.4) % 360 + 360) % 360
    orbitEl = Math.max(5, Math.min(85, orbitEl + dy * 0.3))
    return
  }
  getMouse(event)
  raycaster.setFromCamera(mouse, camera)

  // hover 反馈
  if (!isDragging) {
    const handles = [
      { mesh: azimuthHandle, glow: azGlow, name: 'azimuth' },
      { mesh: elevationHandle, glow: elGlow, name: 'elevation' },
      { mesh: distanceHandle, glow: distGlow, name: 'distance' },
    ]
    let found: string | null = null
    for (const h of handles) {
      if (h.mesh && raycaster.intersectObject(h.mesh).length > 0) { found = h.name; break }
    }
    if (hoveredHandle && hoveredHandle !== found) {
      const prev = handles.find(h => h.name === hoveredHandle)
      if (prev && prev.mesh) prev.mesh.scale.setScalar(1)
    }
    if (found) {
      const cur = handles.find(h => h.name === found)
      if (cur && cur.mesh) cur.mesh.scale.setScalar(1.15)
      renderer.domElement.style.cursor = 'grab'
    } else {
      renderer.domElement.style.cursor = 'default'
    }
    hoveredHandle = found
    return
  }

  // 拖拽各球（仿 ComfyUI）
  const plane = new THREE.Plane()
  const intersect = new THREE.Vector3()
  if (dragTarget === 'azimuth') {
    // 水平面投影算角度
    plane.setFromNormalAndCoplanarPoint(new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 0))
    if (raycaster.ray.intersectPlane(plane, intersect)) {
      let angle = Math.atan2(intersect.x, intersect.z) * 180 / Math.PI
      if (angle < 0) angle += 360
      azimuth.value = Math.max(0, Math.min(360, angle))
    }
  } else if (dragTarget === 'elevation') {
    // ELEV_ARC_X 平面投影算垂直角
    const elevPlane = new THREE.Plane(new THREE.Vector3(1, 0, 0), -ELEV_ARC_X)
    if (raycaster.ray.intersectPlane(elevPlane, intersect)) {
      const relY = intersect.y - CENTER.y
      const relZ = intersect.z
      let angle = Math.atan2(relY, relZ) * 180 / Math.PI
      angle = Math.max(-30, Math.min(60, angle))
      elevation.value = angle
    }
  } else if (dragTarget === 'distance') {
    // 鼠标 Y 控制距离
    const newDist = 5 - mouse.y * 5
    distance.value = Math.max(0, Math.min(10, Math.round(newDist * 10) / 10))
  }
}

function onPointerUp() {
  if (orbitDragging) {
    orbitDragging = false
    if (renderer) renderer.domElement.style.cursor = 'default'
    return
  }
  if (isDragging) {
    isDragging = false
    dragTarget = null
    const handles = [
      { mesh: azimuthHandle, glow: azGlow },
      { mesh: elevationHandle, glow: elGlow },
      { mesh: distanceHandle, glow: distGlow },
    ]
    handles.forEach(h => { if (h.mesh) h.mesh.scale.setScalar(1) })
    if (renderer) renderer.domElement.style.cursor = 'default'
  }
}

function onTouchStart(e: TouchEvent) {
  e.preventDefault()
  onPointerDown({ clientX: e.touches[0].clientX, clientY: e.touches[0].clientY } as MouseEvent)
}
function onTouchMove(e: TouchEvent) {
  e.preventDefault()
  onPointerMove({ clientX: e.touches[0].clientX, clientY: e.touches[0].clientY } as MouseEvent)
}

function loadImage(url: string) {
  if (!planeMat || !imagePlane || !imageFrame) return
  const img = new Image()
  if (!url.startsWith('data:')) img.crossOrigin = 'anonymous'
  img.onload = () => {
    const tex = new THREE.Texture(img)
    tex.colorSpace = THREE.SRGBColorSpace
    tex.needsUpdate = true
    if (planeMat) {
      planeMat.map = tex
      planeMat.color.set(0xffffff)
      planeMat.needsUpdate = true
    }
    const ar = img.width / img.height
    const maxSize = 1.5
    let scaleX = 1.2, scaleY = 1.2
    if (ar > 1) { scaleX = maxSize; scaleY = maxSize / ar }
    else { scaleY = maxSize; scaleX = maxSize * ar }
    if (imagePlane) imagePlane.scale.set(scaleX, scaleY, 1)
    if (imageFrame) imageFrame.scale.set(scaleX, scaleY, 1)
  }
  img.onerror = () => {
    if (planeMat) { planeMat.map = null; planeMat.color.set(0xE93D82); planeMat.needsUpdate = true }
  }
  img.src = url
}

// 滑条改变 → 同步 3D 场景（rAF 节流，避免拖动时响应式风暴）
let _rafPending = false
function scheduleUpdate() {
  if (_rafPending) return
  _rafPending = true
  requestAnimationFrame(() => {
    _rafPending = false
    promptText.value = generatePrompt()
    updateVisuals()
    notify()
  })
}
watch([azimuth, elevation, distance], scheduleUpdate)
function onSliderChange() { scheduleUpdate() }

function reset() {
  azimuth.value = 0
  elevation.value = 0
  distance.value = 5
  // 重置观察相机轨道
  orbitAz = Math.atan2(4, 4) * 180 / Math.PI
  orbitEl = 35
  orbitDist = 6.5
}

onMounted(() => {
  promptText.value = generatePrompt()
  initThree()
})
onUnmounted(() => {
  if (animationId !== null) cancelAnimationFrame(animationId)
  if (renderer) {
    renderer.dispose()
    if (renderer.domElement.parentElement) renderer.domElement.parentElement.removeChild(renderer.domElement)
  }
  window.removeEventListener('mousemove', onPointerMove)
  window.removeEventListener('mouseup', onPointerUp)
  if (renderer) renderer.domElement.removeEventListener('contextmenu', onContextMenu)
})
</script>

<template>
  <div class="space-y-3">
    <!-- 3D 场景 -->
    <div ref="wrapRef" class="relative w-full h-72 rounded-2xl overflow-hidden" style="background:#0a0a0f"></div>

    <!-- 提示词预览 -->
    <div class="text-[11px] font-mono text-gray-400 px-2 py-1.5 bg-gray-900/60 rounded-lg truncate" :title="promptText">{{ promptText }}</div>

    <!-- 滑条双控 -->
    <div class="space-y-2 px-1">
      <div class="flex items-center gap-3">
        <span class="w-16 shrink-0 text-xs" style="color:#E93D82">水平角</span>
        <input type="range" min="0" max="360" step="1" v-model.number="azimuth" @input="onSliderChange" class="flex-1 accent-pink-500 h-1.5 cursor-pointer" />
        <span class="w-12 shrink-0 text-right text-xs font-mono" style="color:#E93D82">{{ Math.round(azimuth) }}°</span>
      </div>
      <div class="flex items-center gap-3">
        <span class="w-16 shrink-0 text-xs" style="color:#00FFD0">垂直角</span>
        <input type="range" min="-30" max="60" step="1" v-model.number="elevation" @input="onSliderChange" class="flex-1 accent-teal-500 h-1.5 cursor-pointer" />
        <span class="w-12 shrink-0 text-right text-xs font-mono" style="color:#00FFD0">{{ Math.round(elevation) }}°</span>
      </div>
      <div class="flex items-center gap-3">
        <span class="w-16 shrink-0 text-xs" style="color:#FFB800">缩放</span>
        <input type="range" min="0" max="10" step="0.1" v-model.number="distance" @input="onSliderChange" class="flex-1 accent-yellow-500 h-1.5 cursor-pointer" />
        <span class="w-12 shrink-0 text-right text-xs font-mono" style="color:#FFB800">{{ distance.toFixed(1) }}</span>
      </div>
    </div>

    <div class="flex justify-between items-center px-1">
      <span class="text-[10px] text-gray-500">拖拽相机调整角度（PC）；右键拖动旋转视角；或滑动条精确微调</span>
      <button @click="reset" class="text-[11px] px-2 py-1 bg-gray-100 dark:bg-gray-700 rounded hover:bg-gray-200 dark:hover:bg-gray-600 cursor-pointer border-0 dark:text-gray-300">重置</button>
    </div>
  </div>
</template>
