/* Mturk2Gforms Appscript Template

This template serves of first structure to write a script generating large number of personalized google forms that you wish to get answered
by MTurk workers.

### Example taks ###
As an example task, we want to collect data about description of image (one word for each image) for 1000 images.
We therefore store these 1000 images in a folder IMGS_FOLDER_ID


Practical Tips:

* In case you have a free google account, your running time will be limited to 6min, which can be unsufficient for some batches. In such case, feel
free to use the MouseClicker.sh script from https://github.com/ymentha14/mturk2gform: the template will append the result of each run to the gform_map.txt
file

*/

///////////////////////////////////////////////////////////////////////////////////////////// CONSTANTS /////////////////////////////////////////////////////////////////////////////////////////////


// number of questions we need to answer (in our case 1000 images)
var N_QUESTIONS = 1000

// number of forms we want to divide the questions on (1000 questions for 100 forms ==> 10 questions pef form)
var N_FORMS = 100

//number of forms to generate with the current appscript run
var N_FORMS_RUN = 3 

// Base for the forms title
var TITLE_BASE = "<Your Title template'"

// ID of the folder containing the images from 0.png to 999.png
var IMGS_FOLDER_ID = "1uPqVyfp_DkOMEqm7_zRyjpDAHycgpu94"



// name of the gform mapping used by mt2gf python package
var GFORM_MAPPING_FILENAME = "gform_map.txt"

var SPREADSHEET_BASE_NAME = "form_result"

var WORKERID_HELP_TEXT = "Enter your worker id here: IMPORTANT make sure it is correctly spelled as this will allow us to map your work to your mturk account and validate your HIT."

var CONFIRMATION_MSG = `
🎉🎉Thank you for completing our survey!🎉🎉
Here is your MTurk completion code. Either copy-paste it or enter the 3 numbers with no space in the required field on the mturk HIT page you come from.

`
///////////////////////////////////////////////////////////////////////////////////////////// END CONSTANTS /////////////////////////////////////////////////////////////////////////////////////////////

///////////////////////////////////////////////////////////////////////////////////////////// HELPER FUNCTIONS /////////////////////////////////////////////////////////////////////////////////////////////

function generate_password(i) {
  /*
  Given a form index (int), generate a number which will act as the confirmation code
  of the google form. This code will be checked downstream in the mt2gf pipeline.
  
  WARNING: Make sure to change this function and that it generates the same output as 
  the one you pass to the Turker class in the mt2gf python script!
  */ 
  var a = i * 837 + 763; // example dummy function, please change
  return a.toString().substr(0,3)
}  
  
  
function chunkify(a, n, balanced) {
  /*
  Splits an array into chunks of size as equal as possible
  */
  if (n < 2)
    return [a];
  var len = a.length,
      out = [],
      i = 0,
      size;
  if (len % n === 0) {
    size = Math.floor(len / n);
    while (i < len) {
      out.push(a.slice(i, i += size));
    }
  }
  else if (balanced) {
    while (i < len) {
      size = Math.ceil((len - i) / n--);
      out.push(a.slice(i, i += size));
    }
  }
  else {
    n--;
    size = Math.floor(len / n);
    if (len % size === 0)
      size--;
    while (i < size * n) {
      out.push(a.slice(i, i += size));
    }
    out.push(a.slice(size * n));
  }
  return out;
}



function read_gdoc(url) {
  /* read a google doc as a string from its url*/
  var doc = DocumentApp.openByUrl(url);
  var datastring = doc.getBody().getText();
  return datastring
}

function get_next_form_idx() {
  /* determine which form needs to be created according
  to the ones already generated */
  folder = DriveApp.getRootFolder()
  var idxes = []
  var files = folder.getFiles();
  while (files.hasNext()) {
    var file = files.next();
    var name = file.getName();
    if (name.startsWith("Test Form")){
      name = name.split(" ")
      idx = name[name.length-1]
      idxes.push(idx)
    }
  }
  if (idxes.length == 0){
    return 0
  }
  var max_idx = Math.max.apply(Math,idxes)
  return max_idx + 1
}

function create_or_append_to_file(formidx,fileName,content) {
  /*
  Either create a file or append to it in case it already exists
  */
  if (formidx == 0){
    newFile = DriveApp.createFile(fileName,content);//Create a new text file in the root folder
  }
  else {
    var folder = DriveApp.getRootFolder()
    var fileList = folder.getFilesByName(fileName);
    if (fileList.hasNext()) {
      // found matching file - append text
      var file = fileList.next();
      var combinedContent = file.getBlob().getDataAsString() + "\n" + content;
      file.setContent(combinedContent);
    }
  }
}

///////////////////////////////////////////////////////////////////////////////////////////// END HELPER FUNCTIONS /////////////////////////////////////////////////////////////////////////////////////////////


///////////////////////////////////////////////////////////////////////////////////////////// FORMS QUESTIONS FUNCTIONS /////////////////////////////////////////////////////////////////////////////////////////////

function add_demographic(form){
   /**
 * Summary. Adds demographic section to the form
 * @param {form}  form          Form in which writing the question field
 * @title_base {str}            Index of the question.
 * @param {bool}   singleForm    Whether to allow only for one word in the validation
 */
  // Demographic
  form.addSectionHeaderItem()
  .setTitle("User informations")
 
  // Age
  var agevalidation = FormApp.createTextValidation()
  .requireTextMatchesPattern("^[0-9]{2}$")
  .setHelpText('Only digits for the age (ex: "26")')
  .build();
  
  form.addTextItem()
  .setTitle("Age")
  .setHelpText("Your age")
  .setValidation(agevalidation)
  .setRequired(false)

  // Gender  
  var genderitem = form.addMultipleChoiceItem()
  genderitem.setTitle("Sex")
  .setChoices([
        genderitem.createChoice('Male'),
        genderitem.createChoice('Female'),
        genderitem.createChoice('Other')
     ])
  .setHelpText("Your sex")
  .setRequired(false)
 
  // Mothertongue
  var lanvalidation = FormApp.createTextValidation()
  .requireTextMatchesPattern("^[a-z]+$")
  .setHelpText('only lowercase letters (ex: english)')
  .build();
  
  form.addTextItem()
  .setTitle("Mothertongue")
  .setHelpText("Your mothertongue")
  .setValidation(lanvalidation)
  .setRequired(false)
  
}

function create_question_field(question_code,form,singleForm=False){
  /**
 * Summary. Create the question field within the form
 * @param {int}    question_code       Index of the question.
 * @param {gform}  form          Form in which writing the question field
 * @param {bool}   singleForm    Whether to allow only for one word in the validation
 */
  var img_title = question_code.toString() + ".png"

  // image insertion
  var folder = DriveApp.getFolderById(IMGS_FOLDER_ID);
  var imgs = folder.searchFiles('title = "' + img_title + '"')
  var img = imgs.next();
  var check = imgs.hasNext()
  form.addImageItem()
           .setImage(img)
           .setTitle(question_code.toString());

  // regex validation
  var pattern = "^[a-z]+$"
  var helptext = 'Non valid format! Only lower-case letters a-z'

  var validation = FormApp.createTextValidation()
  .requireTextMatchesPattern(pattern)
  .setHelpText(helptext)
  .build();

  form.addTextItem()
  .setTitle(question_code.toString() + " (question above)")
  .setRequired(true)
  .setValidation(validation);
}

function create_form(questions_codes,formidx,singleForm=false) {
  /* Create a google form

  Args:
  questions_codes (list of int): list of the indexes of the questions present in the form
  number (int): index of the form
  opt_title (str): optional title to add
  singleForm (Bool): whether to accept a single word per question (3 otherwise)
  */

  // Title and description
  var title = TITLE_BASE + formidx;
  var desc = " <The description of your form here> "

  var form = FormApp.create(title)
  .setTitle(title)
  .setDescription(desc);


  // Worker ID
  var item = "Worker ID"
  var validation = FormApp.createTextValidation()
  .requireTextMatchesPattern("^A[A-Z0-9]+$")
  .setHelpText('MTurk Ids are exclusivels cap letters and numbers.')
  .build();

  form.addTextItem()
  .setTitle(item)
  .setRequired(true)
  .setValidation(validation)
  .setHelpText(WORKERID_HELP_TEXT)
  ;
  
  // Demographic infos
  add_demographic(form)
 
  // Subtitle
  form.addSectionHeaderItem()
  .setTitle("Questions")

  // Questions Fields
  questions_codes.forEach(question_code => create_question_field(question_code,form,singleForm))

  // Completion code
  var password = generate_password(formidx);
  form.setConfirmationMessage(CONFIRMATION_MSG + password)
  form.setShowLinkToRespondAgain(false)

  // Update the form's answers location to a google spreadsheet
  // This step is crucial as mt2gf will fetch the result in this spreadsheet
  var ss = SpreadsheetApp.create(SPREADSHEET_BASE_NAME+formidx.toString());
  form.setDestination(FormApp.DestinationType.SPREADSHEET, ss.getId())
  var res_url = ss.getUrl(); // url to the form result spreadsheet

  // Extract the url to the form
  var url = form.getPublishedUrl();
  var short_url = form.shortenFormUrl(url)
  
  // Store the url to the form and its corresponding spreadsheet url to 
  short_url = formidx.toString() + "," + short_url + "," + res_url  
  create_or_append_to_file(formidx,GFORM_MAPPING_FILENAME,short_url)
}


function create_forms() {
  /*
  Create the forms
  */
  
  // Codes for the questions
  var questions_codes = [...Array(N_QUESTIONS).keys()];
  
  // Create the forms chunks (which questions go to which form)
  questions_codes = chunkify(questions_codes,N_FORMS,true)
  
  // Determines what is the next form to create given previous runs
  var next_form_idx = get_next_form_idx();  
  
  // We need to generate the next N_FORMS_RUN forms following next_form_idx
  questions_codes = questions_codes.slice(next_form_idx,next_form_idx+N_FORMS_RUN)

  // Create one form for each of these chunks
  questions_codes.map(function(chunk,i) {return create_form(chunk,i+next_form_idx,"",true)})

};


