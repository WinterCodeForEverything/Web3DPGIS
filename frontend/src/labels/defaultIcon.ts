// The picture of a point label that has no icon of its own: a blue map pin, so every point label shows an icon, never a bare dot.
const SVG = `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24">
<path d="M12 23s-7.5-7-7.5-13a7.5 7.5 0 0 1 15 0c0 6-7.5 13-7.5 13z" fill="#1e90ff" stroke="#0b3d91" stroke-width="1"/>
<circle cx="12" cy="10" r="3" fill="#fff"/></svg>`

export const DEFAULT_ICON_URL = `data:image/svg+xml;charset=utf-8,${encodeURIComponent( SVG )}`

/** The image to show for a point label. */
export const iconUrlOf = ( label: { icon_url: string | null } ) => label.icon_url || DEFAULT_ICON_URL
