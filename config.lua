---@class MapHudColour
---@field name string
---@field id integer
---@field colour string

return {
    -- Commands
    postalCommand = 'postal', -- /postal <code> sets a waypoint to that postal

    -- Map and HUD colours replaced with the Cobalt palette: GTA hud colour name, its id, and the hex colour to use
    ---@type MapHudColour[]
    hudColours = {
        { name = 'HUD_COLOUR_FREEMODE', id = 116, colour = '#5078D7' },
        { name = 'HUD_COLOUR_FREEMODE_DARK', id = 123, colour = '#23365F' },
        { name = 'HUD_COLOUR_WAYPOINT', id = 142, colour = '#5078D7' },
    },
}
