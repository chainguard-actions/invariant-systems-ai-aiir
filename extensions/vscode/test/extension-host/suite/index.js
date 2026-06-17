const path = require('node:path');
const Mocha = require('mocha');

async function run() {
    const grep = process.env.AIIR_EXTENSION_HOST_GREP?.trim();
    const mocha = new Mocha({
        ui: 'bdd',
        color: true,
        timeout: 20000,
        grep: grep || undefined,
    });

    mocha.addFile(path.resolve(__dirname, 'commands.test.js'));

    await new Promise((resolve, reject) => {
        mocha.run(failures => {
            if (failures > 0) {
                reject(new Error(`${failures} extension-host test(s) failed.`));
                return;
            }

            resolve();
        });
    });
}

module.exports = { run };
