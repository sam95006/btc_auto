// Reference helper matching patched zeabur/cli UploadZipToService prepare URL parsing.
package main

import (
	"fmt"
	"regexp"
)

var deploymentIDFromPrepareURL = regexp.MustCompile(`/deployments/([0-9a-fA-F]{24})`)

func ExtractDeploymentIDFromPrepareURL(rawURL string) (string, error) {
	match := deploymentIDFromPrepareURL.FindStringSubmatch(rawURL)
	if len(match) < 2 {
		return "", fmt.Errorf("deployment id not found in prepare url")
	}
	return match[1], nil
}
