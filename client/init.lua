local config <const> = require 'config'
local postals <const> = require 'shared.postals'

---@param hex string
---@return integer r
---@return integer g
---@return integer b
local function hexToRgb(hex)
    return tonumber(hex:sub(2, 3), 16), tonumber(hex:sub(4, 5), 16), tonumber(hex:sub(6, 7), 16)
end

---@type { id: integer, r: integer, g: integer, b: integer, a: integer }[]
local stockColours <const> = {}

for _, hudColour in ipairs(config.hudColours) do
    local stockR <const>, stockG <const>, stockB <const>, stockA <const> = GetHudColour(hudColour.id)
    stockColours[#stockColours + 1] = { id = hudColour.id, r = stockR, g = stockG, b = stockB, a = stockA }

    local r <const>, g <const>, b <const> = hexToRgb(hudColour.colour)
    ReplaceHudColourWithRgba(hudColour.id, r, g, b, 255)
end

---@param code string?
local function setPostalWaypoint(code)
    if not code then
        SetWaypointOff()
        exports.cobalt_core:Notify({ description = locale('postal.cleared'), type = 'inform' })
        return
    end

    local postal <const> = postals.find(code)
    if not postal then
        exports.cobalt_core:Notify({ description = locale('postal.unknown', code), type = 'error' })
        return
    end

    SetNewWaypoint(postal.x, postal.y)
    exports.cobalt_core:Notify({ description = locale('postal.set', postal.code), type = 'success' })
end

RegisterCommand(config.postalCommand, function(_, args)
    setPostalWaypoint(args[1])
end, false)

local function addPostalSuggestion()
    TriggerEvent('chat:addSuggestion', '/' .. config.postalCommand, locale('postal.suggestion'), {
        { name = locale('postal.code'), help = locale('postal.code_help') },
    })
end

addPostalSuggestion()

AddEventHandler('onClientResourceStart', function(resource)
    if resource == 'cobalt_chat' then
        addPostalSuggestion()
    end
end)

AddEventHandler('onResourceStop', function(resource)
    if resource ~= cache.resource then return end

    for _, stock in ipairs(stockColours) do
        ReplaceHudColourWithRgba(stock.id, stock.r, stock.g, stock.b, stock.a)
    end

    TriggerEvent('chat:removeSuggestion', '/' .. config.postalCommand)
end)

---@param coords? vector3
---@return MapPostal postal
---@return number distance
exports('GetNearestPostal', function(coords)
    return postals.nearest(coords or GetEntityCoords(cache.ped))
end)
