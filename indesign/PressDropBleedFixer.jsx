/*
PressDrop Bleed Fixer (v2.3 - Alignment Fix)

Fixes:
- Forces Ruler Origin to Page (0,0 = Top Left of Trim) so math is always correct.
- ALWAYS creates the image frame at the Bleed Line (not Trim), so bleed is visible.
- Centers content to ensure the mirrored edges align perfectly.
*/

if (typeof JSON === "undefined" || !JSON) {
  JSON = {};
}
if (!JSON.parse) {
  JSON.parse = function (s) { return eval("(" + s + ")"); };
}

#target "InDesign"

var PRESSDROP_JOB_JSON_PATH = typeof PRESSDROP_JOB_JSON_PATH !== "undefined" ? PRESSDROP_JOB_JSON_PATH : null;
var PRESSDROP_AUTO_GENERATIVE_FILL = typeof PRESSDROP_AUTO_GENERATIVE_FILL !== "undefined" ? PRESSDROP_AUTO_GENERATIVE_FILL : null;
var PRESSDROP_OUTLINE_TEXT = typeof PRESSDROP_OUTLINE_TEXT !== "undefined" ? PRESSDROP_OUTLINE_TEXT : null;

function readTextFile(file) {
  file.encoding = "UTF-8";
  file.open("r");
  var text = file.read();
  file.close();
  return text;
}

function toPoints(value, unit) {
  unit = (unit || "in").toLowerCase();
  if (unit === "in" || unit === "inch" || unit === "inches") return value * 72.0;
  if (unit === "mm" || unit === "millimeter" || unit === "millimeters") return value * 72.0 / 25.4;
  if (unit === "pt" || unit === "pts" || unit === "point" || unit === "points") return value;
  return value * 72.0;
}

function getBleedBounds(pageBounds, bleedPts) {
  // pageBounds is [y1, x1, y2, x2] relative to the ruler origin.
  // If we force ruler to page, pageBounds is usually [0, 0, H, W].
  // So Bleed Bounds should be [-Top, -Left, H+Bottom, W+Right].
  return [
    pageBounds[0] - bleedPts.top,
    pageBounds[1] - bleedPts.left,
    pageBounds[2] + bleedPts.bottom,
    pageBounds[3] + bleedPts.right
  ];
}

function parsePages(spec, maxPages) {
    spec = (spec || "1").toLowerCase().replace(/\s/g, "");
    if (spec === "all" || spec === "*") {
        var all = [];
        for (var i = 1; i <= maxPages; i++) all.push(i);
        return all;
    }
    var pages = [];
    var parts = spec.split(",");
    for (var i = 0; i < parts.length; i++) {
        var part = parts[i];
        if (part.indexOf("-") > -1) {
            var range = part.split("-");
            var start = parseInt(range[0]);
            var end = parseInt(range[1]);
            if (!isNaN(start) && !isNaN(end)) {
                end = Math.min(end, maxPages);
                for (var j = start; j <= end; j++) pages.push(j);
            }
        } else {
            var p = parseInt(part);
            if (!isNaN(p) && p <= maxPages) pages.push(p);
        }
    }
    if (pages.length === 0) return [1];
    return pages;
}

function pickJobFile() {
  if (PRESSDROP_JOB_JSON_PATH) {
    var preselected = File(PRESSDROP_JOB_JSON_PATH);
    if (preselected.exists) return preselected;
  }
  return File.openDialog("Select a PressDrop job JSON (*.job.json)", "JSON:*.json");
}

function runGenerativeFill() {
  var actionNames = ["Generative Fill", "Generate Image", "Generate Fill"];
  for (var i = 0; i < actionNames.length; i++) {
    var action = app.menuActions.itemByName(actionNames[i]);
    if (action && action.isValid) {
      action.invoke();
      return true;
    }
  }
  return false;
}

function outlineAllText(doc) {
  var outlined = false;
  for (var i = doc.stories.length - 1; i >= 0; i--) {
    var story = doc.stories[i];
    try {
      if (story && story.texts && story.texts.length > 0) {
        story.texts[0].createOutlines();
        outlined = true;
      }
    } catch (e) {
      // ignore outline failures
    }
  }
  return outlined;
}

function main() {
  var jobFile = pickJobFile();
  if (!jobFile) return;

  var job = JSON.parse(readTextFile(jobFile));
  var autoFill = false;
  if (job && job.indesign && job.indesign.auto_generative_fill) autoFill = true;
  if (PRESSDROP_AUTO_GENERATIVE_FILL !== null) autoFill = PRESSDROP_AUTO_GENERATIVE_FILL === true;
  var outlineText = false;
  if (job && job.indesign && job.indesign.outline_text) outlineText = true;
  if (PRESSDROP_OUTLINE_TEXT !== null) outlineText = PRESSDROP_OUTLINE_TEXT === true;

  // 1. Setup Document Dimensions
  var unit = job.layout.trim.unit || "in";
  var trimW = toPoints(job.layout.trim.w, unit);
  var trimH = toPoints(job.layout.trim.h, unit);

  var bleedPts = {
    top: toPoints(job.layout.bleed.top, unit),
    right: toPoints(job.layout.bleed.right, unit),
    bottom: toPoints(job.layout.bleed.bottom, unit),
    left: toPoints(job.layout.bleed.left, unit)
  };

  var outDir = Folder(job.output.dir);
  if (!outDir.exists) outDir.create();
  var outIndd = File(outDir.fsName + "/" + job.output.basename + ".indd");

  var doc = app.documents.add();
  
  // CRITICAL: Reset Rulers to "Page" so (0,0) is always Top-Left of the Trim.
  // This prevents the frame from jumping to random places on different computers.
  doc.viewPreferences.rulerOrigin = RulerOrigin.PAGE_ORIGIN;
  doc.viewPreferences.horizontalMeasurementUnits = MeasurementUnits.POINTS;
  doc.viewPreferences.verticalMeasurementUnits = MeasurementUnits.POINTS;
  
  doc.documentPreferences.pageWidth = trimW;
  doc.documentPreferences.pageHeight = trimH;
  doc.documentPreferences.pagesPerDocument = 1;
  doc.documentPreferences.facingPages = false;

  doc.documentPreferences.documentBleedTopOffset = bleedPts.top;
  doc.documentPreferences.documentBleedInsideOrLeftOffset = bleedPts.left;
  doc.documentPreferences.documentBleedBottomOffset = bleedPts.bottom;
  doc.documentPreferences.documentBleedOutsideOrRightOffset = bleedPts.right;

  // 2. Process Inputs
  if (!job.inputs || job.inputs.length < 1) {
      alert("No inputs found in Job file.");
      return;
  }
  
  var inputPath = job.inputs[0].path;
  var inputFile = File(inputPath);
  
  if (!inputFile.exists) {
      alert("Error: Input file not found at " + inputPath);
      return;
  }

  var ext = inputFile.name.split(".").pop().toLowerCase();
  
  var actualPageCount = 1;
  if (ext === "pdf") {
       var tempFrame = doc.pages[0].place(inputFile)[0];
       if (tempFrame.pdfAttributes) {
            actualPageCount = tempFrame.pdfAttributes.pageCount;
       }
       tempFrame.parent.remove(); 
  }

  var pagesToPlace = parsePages(job.inputs[0].pages, actualPageCount);
  
  while (doc.pages.length < pagesToPlace.length) {
      doc.pages.add();
  }

  // 3. Place Pages
  for (var i = 0; i < pagesToPlace.length; i++) {
      var pageNum = pagesToPlace[i];
      var docPage = doc.pages[i];
      
      // FIX: Always use the BLEED bounds for the frame, regardless of fit mode.
      // This ensures the frame is large enough to show the mirror/bleed we generated.
      var targetBounds = getBleedBounds(docPage.bounds, bleedPts);

      var frame = docPage.rectangles.add();
      frame.geometricBounds = targetBounds;
      
      try {
          app.pdfPlacePreferences.pageNumber = pageNum;
          app.pdfPlacePreferences.pdfCrop = PDFCrop.CROP_MEDIA; // Ensure we read the full bleed box from the PDF
          frame.place(inputFile);
          
          // FIX: Center Content. Since the PDF was generated with symmetric bleed,
          // centering it in the bleed frame aligns Trim-to-Trim perfectly.
          frame.fit(FitOptions.CENTER_CONTENT);
          
          // Optional: If you want to force it to fill the bleed box exactly
          // frame.fit(FitOptions.FILL_PROPORTIONALLY); 

          if (autoFill) {
            frame.select();
            var invoked = runGenerativeFill();
            if (!invoked) {
              alert("Generative Fill menu not found. Open it manually (Window > Generative Fill).");
            }
          }
          
      } catch(e) {
          frame.contents = "Error placing page " + pageNum;
      }
  }

  if (outlineText) {
    var outlined = outlineAllText(doc);
    if (!outlined) {
      alert("No editable text found to outline. PDFs placed as links are not editable.");
    }
  }

  doc.save(outIndd);
  alert("Success! Created: " + outIndd.name);
}

try {
  app.scriptPreferences.userInteractionLevel = UserInteractionLevels.INTERACT_WITH_ALL;
  main();
} catch (e) {
  alert("Critical Error: " + e.message + "\nLine: " + e.line);
}
