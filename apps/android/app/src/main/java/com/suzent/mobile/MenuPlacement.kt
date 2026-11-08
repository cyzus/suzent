package com.suzent.mobile

/**
 * Where a long-press menu should sit.
 *
 * The point is the press, in window pixels. The menu is then shifted so its
 * measured size stays inside the safe area. A menu taller or wider than that
 * area keeps the safe origin and reports the area as its maximum size, so the
 * panel can scroll instead of drawing under the system bars.
 */
data class MenuPlacement(val x: Int, val y: Int, val maxWidth: Int, val maxHeight: Int)

fun placeMenu(
    anchorX: Int,
    anchorY: Int,
    menuWidth: Int,
    menuHeight: Int,
    windowWidth: Int,
    windowHeight: Int,
    insetLeft: Int = 0,
    insetTop: Int = 0,
    insetRight: Int = 0,
    insetBottom: Int = 0,
    margin: Int = 0,
    touchGap: Int = 0,
): MenuPlacement {
    val safeLeft = insetLeft + margin
    val safeTop = insetTop + margin
    val safeRight = windowWidth - insetRight - margin
    val safeBottom = windowHeight - insetBottom - margin
    val availableWidth = (safeRight - safeLeft).coerceAtLeast(0)
    val availableHeight = (safeBottom - safeTop).coerceAtLeast(0)
    val width = menuWidth.coerceIn(0, availableWidth)
    val height = menuHeight.coerceIn(0, availableHeight)
    val maxX = safeLeft + (availableWidth - width)
    val maxY = safeTop + (availableHeight - height)
    val preferredY = when {
        touchGap == 0 -> anchorY
        anchorY + touchGap + height <= safeBottom -> anchorY + touchGap
        anchorY - touchGap - height >= safeTop -> anchorY - touchGap - height
        else -> anchorY
    }
    return MenuPlacement(
        x = anchorX.coerceIn(safeLeft, maxX),
        y = preferredY.coerceIn(safeTop, maxY),
        maxWidth = availableWidth,
        maxHeight = availableHeight,
    )
}
