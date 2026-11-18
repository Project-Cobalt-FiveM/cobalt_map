---@meta

---@class MapPostal
---@field code string
---@field x number
---@field y number

---@class CobaltMapExports
local CobaltMapExports = {}

---**Client.** Returns the postal nearest to the coords, or to the player.
---@param coords? vector3
---@return MapPostal postal
---@return number distance meters
function CobaltMapExports:GetNearestPostal(coords) end

exports.cobalt_map = CobaltMapExports
