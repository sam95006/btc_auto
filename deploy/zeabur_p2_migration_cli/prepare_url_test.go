package main

import "testing"

func TestExtractDeploymentIDFromPrepareURL(t *testing.T) {
	url := "https://zeabur.com/projects/aaaaaaaaaaaaaaaaaaaaaaaa/services/bbbbbbbbbbbbbbbbbbbbbbbb/deployments/6a89a69fa158dec40572a046?envID=69d559b6474db8a99d6dd6bf"
	got, err := ExtractDeploymentIDFromPrepareURL(url)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	want := "6a89a69fa158dec40572a046"
	if got != want {
		t.Fatalf("got %q want %q", got, want)
	}
}

func TestExtractDeploymentIDFromPrepareURLMissing(t *testing.T) {
	_, err := ExtractDeploymentIDFromPrepareURL("https://zeabur.com/projects/x/services/y")
	if err == nil {
		t.Fatal("expected error")
	}
}
