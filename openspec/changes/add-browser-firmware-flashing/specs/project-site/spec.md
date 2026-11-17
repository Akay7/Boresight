# Spec Delta

## Purpose

Presents the project's documentation as a navigable website built from
the READMEs that already document it, published on GitHub Pages and
servable locally, with the firmware flasher as one of its pages.

## ADDED Requirements

### Requirement: The READMEs are published as one site
The project SHALL build a documentation site whose pages are the main
README and the READMEs of the ESP32-CAM firmware, the printable case and
the Pi gun, with navigation between them and search. The READMEs SHALL
stay the single source: the site SHALL be generated from them, not kept
as a second copy.

#### Scenario: A README section appears on the site
- **WHEN** a section is added to the ESP32-CAM firmware README and the
  site is built
- **THEN** the site's firmware page contains that section, with no other
  file edited

### Requirement: Links and images work on the site
Links and images in the READMEs that point at other files in the
repository SHALL work on the site: another README SHALL lead to its page,
an image SHALL show, and any other file SHALL lead to that file in the
repository on GitHub. The site build SHALL fail on a link it cannot
resolve, rather than publish a broken one.

#### Scenario: The flashing diagram shows
- **WHEN** the main README's wiring image is viewed on the site
- **THEN** the image is displayed

#### Scenario: A source file link leads to GitHub
- **WHEN** a README links a source file such as a firmware module
- **THEN** the site's link opens that file in the repository on GitHub

#### Scenario: A broken link stops the build
- **WHEN** a README links a file that does not exist
- **THEN** the site build fails naming the link

### Requirement: The site is published from the main branch
The project SHALL publish the site on GitHub Pages from every push to
the main branch and from every version tag, so the published docs
follow the code. Its flashing page SHALL offer the latest released
firmware image.

#### Scenario: Docs follow main
- **WHEN** a README change is pushed to the main branch
- **THEN** the published site shows it once the publishing run completes

### Requirement: The site can be served locally
The project SHALL provide a single command that serves the site on
`localhost` from a checkout, rebuilding when a README changes, so the
docs can be previewed and the flasher used with a local build.

#### Scenario: The site is previewed locally
- **WHEN** the documented command is run in a checkout
- **THEN** the site is served on `localhost`, and editing a README
  updates the served page
