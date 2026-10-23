export abstract class BaseConnector {
    send<T>(value: T): T { return value; }
}
export class ClientConnector extends BaseConnector {
    send<T>(value: T): T { return super.send(value); }
    fetch(value: string) {
        const callback = () => this.send(value);
        return callback();
    }
}
export function createRequest(connector: ClientConnector) {
    return (command: string) => connector.fetch(command);
}
declare const window: { requestData: (command: string) => string };
const connector = new ClientConnector();
window.requestData = createRequest(connector);
export function entry() { return window.requestData('fixture/query'); }
export function map() { return 0; }
