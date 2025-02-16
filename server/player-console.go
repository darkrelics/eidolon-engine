/*
Eidolon Engine

Copyright 2024-2025 Jason Robinson

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package main

import (
	"strings"
)

func (p *Player) Console() {
	for {
		characterCount := len(p.characterList)
		var choice string

		p.toPlayer <- "\n=====Console=====\n"
		if characterCount == 0 {
			p.toPlayer <- "1) Change Password\n"
			p.toPlayer <- "2) Create Character\n"
			p.toPlayer <- "9) Quit\n"
		} else {
			p.toPlayer <- "1) Change Password\n"
			p.toPlayer <- "2) Create Character\n"
			p.toPlayer <- "3) Select Character\n"
			p.toPlayer <- "9) Quit\n"
		}
		p.toPlayer <- "\nEnter your choice: "

		choice = <-p.fromPlayer

		switch strings.TrimSpace(choice) {
		case "9":
			p.toPlayer <- "\nGoodbye!\n"
			p.Stop()
			return // Exit the console loop

		default:
			p.toPlayer <- "Invalid choice. Please try again.\n"
			//loop and present choices again
			continue
		}
	}
}
