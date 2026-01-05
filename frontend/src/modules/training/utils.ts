// Basic bounding box type for calculation
interface Box {
  x: number
  y: number
  w: number
  h: number
}

// Annotation subset type for filtering
interface AnnotationLike {
  id: string
  points?: [number, number][]
  score?: number
}

/**
 * Calculates bbox from a list of points
 */
export function getBounds(points: [number, number][]): Box {
  if (!points || !Array.isArray(points) || points.length === 0) {
      return { x: 0, y: 0, w: 0, h: 0 }
  }
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const pt of points) {
    // Handle both [x,y] and {x,y} for robustness
    const x = Array.isArray(pt) ? pt[0] : (pt as { x: number }).x
    const y = Array.isArray(pt) ? pt[1] : (pt as { y: number }).y
    
    if (typeof x !== 'number' || typeof y !== 'number') continue

    minX = Math.min(minX, x)
    minY = Math.min(minY, y)
    maxX = Math.max(maxX, x)
    maxY = Math.max(maxY, y)
  }
  if (minX === Infinity) return { x: 0, y: 0, w: 0, h: 0 }
  return { x: minX, y: minY, w: maxX - minX, h: maxY - minY }
}

/**
 * Calculates Intersection over Union (IoU) for two annotations based on their bounding boxes.
 */
export function calculateIoU(a: AnnotationLike, b: AnnotationLike): number {
  if (!a.points || !b.points) return 0
  const boxA = getBounds(a.points)
  const boxB = getBounds(b.points)

  const xA = Math.max(boxA.x, boxB.x)
  const yA = Math.max(boxA.y, boxB.y)
  const xB = Math.min(boxA.x + boxA.w, boxB.x + boxB.w)
  const yB = Math.min(boxA.y + boxA.h, boxB.y + boxB.h)

  const interW = Math.max(0, xB - xA)
  const interH = Math.max(0, yB - yA)
  const intersection = interW * interH

  const areaA = boxA.w * boxA.h
  const areaB = boxB.w * boxB.h
  const union = areaA + areaB - intersection

  return union === 0 ? 0 : intersection / union
}

/**
 * Filters annotations using Non-Maximum Suppression (NMS).
 * @param annotations List of annotations to filter
 * @param iouThreshold Threshold for overlapping (default 0.3). If overlap > threshold, lower score is removed.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function filterAnnotationsNMS(annotations: any[], iouThreshold: number = 0.3): any[] {
  // 1. Sort by score desc (higher confidence first)
  const sorted = [...annotations].sort((a, b) => (b.score || 0) - (a.score || 0))
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const kept: any[] = []

  for (const candidate of sorted) {
    let keep = true
    for (const existing of kept) {
       const iou = calculateIoU(candidate, existing)
       if (iou > iouThreshold) {
         keep = false
         break
       }
    }
    if (keep) kept.push(candidate)
  }
  return kept
}
