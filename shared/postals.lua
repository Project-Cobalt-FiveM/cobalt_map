local postals <const> = lib.load('data.postals') --[[@as MapPostal[] ]]

---@type table<string, MapPostal>
local byCode <const> = {}
for i = 1, #postals do
    byCode[postals[i].code] = postals[i]
end

local Postals <const> = {}

---@param code string
---@return MapPostal?
function Postals.find(code)
    return byCode[code]
end

---@param coords vector2 | vector3 | { x: number, y: number }
---@return MapPostal postal
---@return number distance
function Postals.nearest(coords)
    local nearest, nearestSq = postals[1], math.huge

    for i = 1, #postals do
        local postal <const> = postals[i]
        local dx <const>, dy <const> = postal.x - coords.x, postal.y - coords.y
        local distanceSq <const> = dx * dx + dy * dy
        if distanceSq < nearestSq then
            nearest, nearestSq = postal, distanceSq
        end
    end

    return nearest, math.sqrt(nearestSq)
end

return Postals
