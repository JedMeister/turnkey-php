#!/bin/bash -e

share=share/keyrings
key=php-sury.org.gpg
URL=https://packages.sury.org/php/apt.gpg

if [[ -d "$share" ]]; then
    # being run from repo
    path=$share
elif [[ -d /usr/share/keyrings ]]; then
    # normal state
    path=/usr/share/keyrings
else
    # just in case
    path=/usr/share/keyrings
fi
keyfile=/usr/share/keyrings/php-sury.org.gpg
wget -O $keyfile https://packages.sury.org/php/apt.gpg
