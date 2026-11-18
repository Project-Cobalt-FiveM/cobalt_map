fx_version 'cerulean'
game 'gta5'
lua54 'yes'
use_experimental_fxv2_oal 'yes'

name 'cobalt_map'
author 'Citgo'
description 'Project Cobalt map: minimap styling and postal codes'
version '1.0.0'

shared_script '@ox_lib/init.lua'

ox_libs { 'locale' }

client_script 'client/init.lua'

files {
    'config.lua',
    'shared/postals.lua',
    'data/postals.lua',
    'locales/*.json',
}

dependencies {
    'ox_lib',
}
