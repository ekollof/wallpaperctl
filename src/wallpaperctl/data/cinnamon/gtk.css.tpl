/* Dynamic GTK3 theme generated from wallpaper colors */
/* Generated on wallpaperctl */
/* Base colors: bg=$color0, fg=$color7, accent=$color4 */

/* Define dynamic theme colors first */
@define-color theme_base_color #$color0;
@define-color theme_bg_color #$color0;
@define-color theme_fg_color #$color7;  
@define-color theme_text_color #$color7;
@define-color theme_selected_bg_color #$color4;
@define-color theme_selected_fg_color #$color7;
@define-color insensitive_bg_color shade(@theme_bg_color, 0.95);
@define-color insensitive_fg_color shade(@theme_fg_color, 0.6);
@define-color borders shade(@theme_bg_color, 0.8);
@define-color success_color #$color4;
@define-color warning_color #$color4; /* Use accent color instead of orange */
@define-color error_color #$color1; /* Use red from color scheme */

/* Define our dynamic color variables for metacity compatibility */
@define-color base_color #$color0;
@define-color bg_color #$color0;
@define-color fg_color #$color7;
@define-color text_color #$color7;
@define-color selected_bg_color #$color4;
@define-color selected_fg_color #$color7;
@define-color theme_base_color #$color0;
@define-color theme_bg_color #$color0;
@define-color theme_fg_color #$color7;
@define-color theme_text_color #$color7;
@define-color theme_selected_bg_color #$color4;
@define-color theme_selected_fg_color #$color7;

/* Window manager specific color definitions for metacity */
@define-color wm_title #$color7;
@define-color wm_title_unfocused shade(#$color7, 0.7);
@define-color wm_bg #$color4;  /* Use accent color for WM backgrounds */
@define-color wm_bg_unfocused mix(#$color4, #$color0, 0.7);
@define-color wm_border #$color4;
@define-color wm_border_unfocused shade(#$color4, 0.85);
@define-color wm_highlight #$color7;

@define-color insensitive_bg_color shade(#$color0, 0.95);
@define-color insensitive_fg_color shade(#$color7, 0.6);
@define-color borders shade(#$color0, 0.8);
@define-color warning_color #$color4; /* Use accent color instead of orange */
@define-color error_color #$color1; /* Use red from color scheme */
@define-color success_color #$color2; /* Use green from color scheme */

/* Window and container backgrounds */
window,
.background {
    background-color: #$color0;
    color: #$color7;
}

/* Headers and titlebars - Modern Material Design inspired styling */
headerbar,
.titlebar {
    transition: background-color 200ms ease-out, color 200ms ease-out;
    border-radius: 8px 8px 0 0;
    /* Layered shadows for depth - inspired by Material Design */
    box-shadow: inset 0 1px rgba($color7_rgb, 0.1),
                0 1px 3px rgba(0, 0, 0, 0.12),
                0 1px 2px rgba(0, 0, 0, 0.24);
    /* Sophisticated gradient with accent highlights */
    background: linear-gradient(to bottom,
                mix(#$color4, #$color0, 0.35),
                mix(#$color4, #$color0, 0.2),
                mix(#$color0, #$color4, 0.05));
    color: #$color7;
    /* Enhanced accent border */
    border-bottom: 2px solid rgba($accent_rgb, 0.8);
    min-height: 44px;
    padding: 6px 12px;
}

headerbar:backdrop,
.titlebar:backdrop {
    /* Subtle backdrop state */
    background: linear-gradient(to bottom,
                mix(#$color4, #$color0, 0.2),
                mix(#$color0, #$color4, 0.1));
    box-shadow: inset 0 1px rgba($color7_rgb, 0.05),
                0 1px 2px rgba(0, 0, 0, 0.08);
    border-bottom: 1px solid rgba($accent_rgb, 0.4);
    color: rgba($color7_rgb, 0.75);
}

headerbar .title,
.titlebar .title {
    color: #$color7;
    font-weight: bold;
    padding: 0 12px;
}

headerbar .subtitle,
.titlebar .subtitle {
    color: rgba($color7_rgb, 0.85);
    font-size: smaller;
    padding: 0 12px;
}

/* Modern window decorations - inspired by Material Design and Materia theme */
decoration {
    transition: background-color 200ms ease-out, box-shadow 200ms ease-out;
    border-radius: 8px 8px 0 0;
    border-width: 0;
    /* Layered shadows for realistic depth */
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15),
                0 4px 12px rgba(0, 0, 0, 0.1),
                0 2px 6px rgba(0, 0, 0, 0.1);
    /* Sophisticated gradient matching headerbar */
    background: linear-gradient(to bottom,
                mix(#$color4, #$color0, 0.35),
                mix(#$color4, #$color0, 0.2),
                mix(#$color0, #$color4, 0.05));
    margin: 8px; /* Space for resize handles */
}

decoration:backdrop {
    /* Reduced shadows for backdrop state */
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08),
                0 2px 6px rgba(0, 0, 0, 0.06),
                0 1px 3px rgba(0, 0, 0, 0.04);
    background: linear-gradient(to bottom,
                mix(#$color4, #$color0, 0.2),
                mix(#$color0, #$color4, 0.1));
}

/* Tiled/maximized windows have no rounded corners or margins */
.tiled decoration,
.tiled-top decoration,
.tiled-right decoration,
.tiled-bottom decoration,
.tiled-left decoration,
.maximized decoration,
.fullscreen decoration {
    border-radius: 0;
    margin: 0;
    /* Simplified shadows for tiled windows */
    box-shadow: 0 0 0 1px rgba($accent_rgb, 0.3);
}

.popup decoration {
    border-radius: 8px;
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.18),
                0 2px 8px rgba(0, 0, 0, 0.12);
}

.ssd decoration {
    /* Server-side decorations with accent outline */
    box-shadow: 0 0 0 1px rgba($accent_rgb, 0.4),
                inset 0 1px rgba($color7_rgb, 0.1);
}

/* Enhanced titlebar styling for server-side decorations */
decoration .titlebar {
    background: linear-gradient(to bottom,
                mix(#$color4, #$color0, 0.35),
                mix(#$color4, #$color0, 0.2),
                mix(#$color0, #$color4, 0.05));
    border-bottom: 2px solid rgba($accent_rgb, 0.6);
    color: #$color7;
    padding: 8px 16px;
    min-height: 36px;
    /* Subtle inner glow and accent highlight */
    box-shadow: inset 0 1px rgba($color7_rgb, 0.12),
                inset 0 -1px rgba($accent_rgb, 0.4);
}

decoration .titlebar:backdrop {
    background: linear-gradient(to bottom,
                mix(#$color4, #$color0, 0.2),
                mix(#$color0, #$color4, 0.1));
    border-bottom: 1px solid rgba($accent_rgb, 0.3);
    color: rgba($color7_rgb, 0.75);
    box-shadow: inset 0 1px rgba($color7_rgb, 0.06),
                inset 0 -1px rgba($accent_rgb, 0.2);
}

/* Modern titlebar buttons - inspired by Material Design */
headerbar button,
.titlebar button {
    transition: all 200ms ease-out;
    min-height: 24px;
    min-width: 24px;
    padding: 6px;
    border-radius: 50%;
    border: none;
    /* Subtle background with hover states */
    background-color: transparent;
    color: rgba($color7_rgb, 0.8);
    box-shadow: none;
}

headerbar button:hover,
.titlebar button:hover {
    background-color: rgba($color7_rgb, 0.1);
    color: #$color7;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

headerbar button:active,
.titlebar button:active {
    background-color: rgba($color7_rgb, 0.2);
    transform: scale(0.95);
}

headerbar button:backdrop,
.titlebar button:backdrop {
    color: rgba($color7_rgb, 0.5);
    background-color: transparent;
}

/* Window control buttons with modern styling */
.titlebutton {
    transition: all 200ms ease-out;
    border-radius: 50%;
    min-height: 20px;
    min-width: 20px;
    padding: 4px;
    margin: 0 2px;
    border: none;
    background-color: transparent;
    color: rgba($color7_rgb, 0.9);
}

.titlebutton:hover {
    background-color: rgba($color7_rgb, 0.15);
    color: #$color7;
}

.titlebutton.close:hover {
    background-color: #e74c3c;
    color: white;
}

.titlebutton.maximize:hover {
    background-color: rgba($accent_rgb, 0.8);
    color: #$color7;
}

.titlebutton.minimize:hover {
    background-color: rgba($accent_rgb, 0.6);
    color: #$color7;
}

.titlebar .subtitle {
    color: shade(#$color7, 0.8);
    font-size: smaller;
}

/* Header bar buttons - Critical for proper theming */
headerbar button,
.titlebar button {
    background: transparent;
    border: none;
    color: #$color7;
    border-radius: 4px;
    padding: 4px 8px;
    min-width: 16px;
    min-height: 16px;
}

headerbar button:hover,
.titlebar button:hover {
    background: rgba($accent_rgb, 0.3);
    color: #$color7;
}

headerbar button:active,
headerbar button:checked,
.titlebar button:active,
.titlebar button:checked {
    background: rgba($accent_rgb, 0.5);
    color: #$color7;
}

headerbar button:backdrop,
.titlebar button:backdrop {
    color: shade(#$color7, 0.6);
}

/* Window control buttons (minimize, maximize, close) */
headerbar .titlebutton,
.titlebar .titlebutton {
    background: transparent;
    border: none;
    color: #$color7;
    padding: 4px;
    min-width: 20px;
    min-height: 20px;
    border-radius: 3px;
}

headerbar .titlebutton:hover,
.titlebar .titlebutton:hover {
    background: rgba($accent_rgb, 0.3);
}

headerbar .titlebutton:active,
.titlebar .titlebutton:active {
    background: rgba($accent_rgb, 0.5);
}

headerbar .titlebutton.close:hover,
.titlebar .titlebutton.close:hover {
    background: #e74c3c;
    color: white;
}

headerbar .titlebutton:backdrop,
.titlebar .titlebutton:backdrop {
    color: shade(#$color7, 0.6);
}

/* Window decorations (for server-side decorations like xterm) */
decoration {
    border-radius: 8px 8px 0 0;
    border-width: 0;
    box-shadow: 0 3px 9px 1px rgba($accent_rgb, 0.4), 0 1px 3px rgba(0, 0, 0, 0.3);
    background: linear-gradient(to bottom,
                mix(#$color4, #$color0, 0.3),
                mix(#$color4, #$color0, 0.15),
                mix(#$color0, #$color4, 0.1));
}

decoration:backdrop {
    box-shadow: 0 2px 6px 1px rgba($accent_rgb, 0.2), 0 1px 3px rgba(0, 0, 0, 0.2);
    background: linear-gradient(to bottom,
                mix(#$color4, #$color0, 0.15),
                mix(#$color0, #$color4, 0.08));
}

.tiled decoration,
.tiled-top decoration,
.tiled-right decoration,
.tiled-bottom decoration,
.tiled-left decoration {
    border-radius: 0;
}

.popup decoration {
    border-radius: 8px;
    box-shadow: 0 1px 6px rgba(0, 0, 0, 0.31);
}

.ssd decoration {
    box-shadow: 0 0 0 1px rgba($accent_rgb, 0.5);
}

/* Window title and controls for server-side decorations */
decoration .titlebar {
    background: linear-gradient(to bottom, 
                shade(#$color0, 1.08), 
                #$color0,
                shade(#$color0, 0.95));
    border-bottom: 1px solid rgba($accent_rgb, 0.6);
    color: #$color7;
    padding: 4px 8px;
    min-height: 32px;
}

decoration .titlebar:backdrop {
    background: linear-gradient(to bottom, 
                shade(#$color0, 1.03), 
                shade(#$color0, 0.98));
    border-bottom: 1px solid rgba($accent_rgb, 0.3);
    color: shade(#$color7, 0.7);
}

/* Buttons */
button {
    background: linear-gradient(to bottom,
                shade(#$color0, 1.15),
                shade(#$color0, 1.05));
    color: #$color7;
    border: 1px solid shade(#$color0, 0.8);
    border-radius: 4px;
    padding: 6px 12px;
}

button:hover {
    background: linear-gradient(to bottom,
                shade(#$color4, 1.1),
                #$color4);
    border-color: shade(#$color4, 0.8);
    color: #$color7;
}

button:active,
button:checked {
    background: linear-gradient(to bottom,
                shade(#$color4, 0.9),
                shade(#$color4, 0.8));
    border-color: shade(#$color4, 0.7);
    color: #$color7;
}

/* Text entries */
entry {
    background-color: shade(#$color0, 1.1);
    color: #$color7;
    border: 1px solid shade(#$color0, 0.8);
    border-radius: 4px;
    padding: 6px 8px;
}

entry:focus {
    border-color: #$color4;
    box-shadow: 0 0 3px rgba($accent_rgb, 0.5);
}

/* Sidebar and lists */
.sidebar {
    background-color: shade(#$color0, 0.95);
    color: #$color7;
    border-right: 1px solid shade(#$color0, 0.8);
}

list,
.list {
    background-color: shade(#$color0, 1.05);
    color: #$color7;
}

list row,
.list row {
    border-bottom: 1px solid shade(#$color0, 0.9);
}

list row:hover,
.list row:hover {
    background-color: shade(#$color4, 0.3);
}

list row:selected,
.list row:selected {
    background-color: #$color4;
    color: #$color7;
}

/* Menus and popups */
menu,
.menu {
    background-color: shade(#$color0, 1.05);
    color: #$color7;
    border: 1px solid shade(#$color0, 0.8);
    border-radius: 6px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
}

menuitem,
.menuitem {
    color: #$color7;
    padding: 6px 12px;
}

menuitem:hover,
.menuitem:hover {
    background-color: #$color4;
    color: #$color7;
}

/* Notebook tabs */
notebook tab {
    background: linear-gradient(to bottom,
                shade(#$color0, 1.1),
                #$color0);
    color: #$color7;
    border: 1px solid shade(#$color0, 0.8);
    border-bottom: none;
    border-radius: 4px 4px 0 0;
    padding: 8px 16px;
}

notebook tab:checked {
    background: linear-gradient(to bottom,
                shade(#$color4, 1.1),
                #$color4);
    border-color: shade(#$color4, 0.8);
    color: #$color7;
}

/* Toolbars */
toolbar {
    background: linear-gradient(to bottom,
                shade(#$color0, 1.1),
                #$color0);
    color: #$color7;
    border-bottom: 1px solid shade(#$color0, 0.8);
    padding: 4px;
}

/* Scrollbars */
scrollbar {
    background-color: shade(#$color0, 0.95);
}

scrollbar slider {
    background-color: shade(#$color4, 0.8);
    border-radius: 6px;
    min-width: 12px;
    min-height: 12px;
}

scrollbar slider:hover {
    background-color: #$color4;
}

/* Progress bars */
progressbar trough {
    background-color: shade(#$color0, 0.9);
    border-radius: 4px;
}

progressbar progress {
    background: linear-gradient(to right, #$color4, shade(#$color4, 1.2));
    border-radius: 4px;
}

/* Check boxes and radio buttons */
checkbutton check,
radiobutton radio {
    background-color: shade(#$color0, 1.1);
    border: 1px solid shade(#$color0, 0.8);
    color: #$color7;
}

checkbutton check:checked,
radiobutton radio:checked {
    background-color: #$color4;
    border-color: shade(#$color4, 0.8);
    color: #$color7;
}

/* Switches */
switch {
    background-color: shade(#$color0, 0.9);
    border: 1px solid shade(#$color0, 0.8);
    border-radius: 12px;
}

switch:checked {
    background-color: #$color4;
    border-color: shade(#$color4, 0.8);
}

switch slider {
    background-color: #$color7;
    border-radius: 50%;
}

/* Selection highlighting */
selection,
*:selected {
    background-color: #$color4;
    color: #$color7;
}

/* Tooltips */
tooltip {
    background-color: shade(#$color0, 1.2);
    color: #$color7;
    border: 1px solid shade(#$color0, 0.8);
    border-radius: 4px;
    padding: 6px 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
}

/* EXCLUDE notifications from GTK theme to preserve system notifications */
.notification,
.notification-banner,
.notification-popup,
.popup-notification,
.notification-applet,
.notification-container,
.notification-content {
    /* Let system handle notification styling completely */
    background-color: inherit !important;
    color: inherit !important;
    border: inherit !important;
    border-radius: inherit !important;
    box-shadow: inherit !important;
}

/* Window frames for CSD applications */
.window-frame {
    border-color: #$color4;
    border-radius: 8px 8px 0 0;
    border-width: 2px;
    border-style: solid;
    box-shadow: 0 2px 8px 3px rgba($accent_rgb, 0.3), 0 4px 16px rgba(0, 0, 0, 0.4);
    margin: 10px;
    background-color: #$color0;
}

.window-frame:backdrop {
    border-color: rgba($accent_rgb, 0.6);
    box-shadow: 0 2px 5px 1px rgba($accent_rgb, 0.2), 0 4px 12px rgba(0, 0, 0, 0.3);
}

.window-frame.tiled {
    border-radius: 0;
    margin: 0;
    box-shadow: none;
}

.window-frame.maximized {
    border-radius: 0;
    margin: 0;
    box-shadow: none;
}

/* Titlebar within window frame */
.window-frame .titlebar {
    border-radius: 7px 7px 0px 0px;
    background: linear-gradient(to bottom, 
                shade(#$color0, 1.08), 
                #$color0,
                shade(#$color0, 0.95));
    border-bottom: 1px solid rgba($accent_rgb, 0.6);
}

.window-frame.tiled .titlebar,
.window-frame.maximized .titlebar {
    border-radius: 0;
}

/* Base styling using defined colors */
window {
    background-color: @theme_bg_color;
    color: @theme_fg_color;
}

/* Ensure symbolic icons inherit text colors properly */
image {
    color: inherit;
}

/* GTK Icon Palette - Apply to all elements */
* {
    -gtk-icon-palette: 
        success @success_color,
        warning @warning_color,
        error @error_color;
}